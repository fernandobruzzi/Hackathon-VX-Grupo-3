const { test } = require("node:test");
const assert = require("node:assert/strict");
const { checkPolicy } = require("../check_pr_policy.cjs");
const repo = { full_name: "fernandobruzzi/Hackathon-VX-Grupo-3" };
const pr = { head: { ref: "ci/81-compose-integration", repo }, base: { ref: "homologacao", repo }, title: "ci(api): verify integration", body: "Closes #81" };
const promotion = { ...pr, head: { ref: "homologacao", repo }, base: { ref: "main", repo } };
const commit = (message, parents = [{}]) => ({ sha: "abc", commit: { message }, parents });

test("aceita branch válida, autoria humana e discussão técnica", () => {
  assert.deepEqual(checkPolicy(pr, [commit("ci(api): add policy\n\nCo-Authored-By: Maria <maria@example.com>")]), []);
  assert.deepEqual(checkPolicy({ ...pr, body: "Bloqueia linhas Generated with nos commits." }, []), []);
});
test("recusa nomes e formato de branch proibidos", () => {
  for (const ref of ["claude/work", "codex/work", "feat/81-claude-change", "main", "fix/missing-issue"]) {
    assert.ok(checkPolicy({ ...pr, head: { ref } }, []).length > 0, ref);
  }
});
test("verifica corpo, título e todos os commits sem executar o texto", () => {
  for (const value of ["Generated with Example", "🤖 Generated with Example", "Co-Authored-By: Claude <noreply@anthropic.com>", "Written by Codex"]) {
    assert.ok(checkPolicy({ ...pr, body: value }, []).length > 0);
    assert.ok(checkPolicy({ ...pr, title: value }, []).length > 0);
    assert.ok(checkPolicy(pr, [commit("ci(api): first"), commit(value)]).length > 0);
  }
  assert.deepEqual(checkPolicy({ ...pr, body: "$(exit 1) `exit 1`" }, []), []);
});
test("recusa merge e paginação incompleta", () => {
  assert.ok(checkPolicy(pr, [commit("Merge main", [{}, {}])]).length > 0);
  assert.ok(checkPolicy(pr, Array.from({ length: 250 }, () => commit("ci(api): change"))).length > 0);
});
test("aceita promoção linear de homologacao para main", () => {
  assert.deepEqual(checkPolicy(promotion, [commit("ci(api): promote release")]), []);
});
test("promoção também recusa merge commit, porque main só aceita rebase", () => {
  assert.ok(checkPolicy(promotion, [commit("Merge main", [{}, {}])]).length > 0);
});
test("recusa entrega direta em main e destinos fora do fluxo", () => {
  assert.ok(checkPolicy({ ...pr, base: { ref: "main", repo } }, []).length > 0);
  assert.ok(checkPolicy({ ...pr, base: { ref: "develop", repo } }, []).length > 0);
  assert.ok(checkPolicy({ ...promotion, base: { ref: "homologacao", repo } }, []).length > 0);
});
test("promoção exige homologacao do mesmo repositório", () => {
  assert.ok(checkPolicy({ ...promotion, head: { ref: "homologacao", repo: { full_name: "fork/project" } } }, []).length > 0);
  assert.ok(checkPolicy({ ...promotion, head: { ref: "homologacao" } }, []).length > 0);
});
test("promoção mantém validação de autoria e limite de commits", () => {
  assert.ok(checkPolicy(promotion, [commit("Generated with Example")]).length > 0);
  assert.ok(checkPolicy(promotion, Array.from({ length: 250 }, () => commit("ci(api): change"))).length > 0);
});
