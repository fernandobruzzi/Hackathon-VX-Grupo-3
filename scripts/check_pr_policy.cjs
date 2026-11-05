// Política compartilhada entre a verificação do PR e os testes locais.
function checkPolicy(pr, commits) {
  const problems = [];
  const branch = pr.head.ref;
  if (!/^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)\/[0-9]+-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(branch)) {
    problems.push("A branch deve usar <type>/<issue>-<slug>.");
  }
  if (/(^|[\/_-])(claude|codex|copilot|chatgpt|cursor)([\/_-]|$)/i.test(branch)) {
    problems.push("Nome de ferramenta de autoria proibido na branch.");
  }
  if (commits.length >= 250) {
    problems.push("PR excede o limite seguro da API de commits; divida a entrega.");
  }
  const texts = [
    ["PR", `${pr.title}\n${pr.body || ""}`],
    ...commits.map(c => [c.sha, c.commit.message]),
  ];
  for (const [label, value] of texts) {
    if (/^\s*(?:[>*_-]\s*)*(?:🤖\s*)?generated\s+(?:with|by)\b/im.test(value) ||
        /^co-authored-by:.*(?:\b(?:claude|codex|copilot|chatgpt|cursor|anthropic|openai)\b)/im.test(value) ||
        /(?:authored|written|created|implemented|assisted)\s+by\s+(?:claude|codex|copilot|chatgpt|cursor)\b/i.test(value)) {
      problems.push(`${label}: atribuição automática proibida.`);
    }
  }
  if (commits.some(c => c.parents.length > 1)) {
    problems.push("PR contém merge commit; atualize por rebase.");
  }
  return problems;
}

module.exports = { checkPolicy };
