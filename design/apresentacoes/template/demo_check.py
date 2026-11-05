"""Confere fora do navegador os números da demo de limiar (mesma semente e mesmo gerador do index.html).
Uso: python3 demo_check.py [magnitudes separadas por vírgula]"""
import math,sys
def imul(a,b): return (a*b)&0xffffffff
def mul(a):
    s=[a&0xffffffff]
    def r():
        s[0]=(s[0]+0x6D2B79F5)&0xffffffff; a=s[0]
        t=imul(a^(a>>15),1|a)
        t=((t+imul(t^(t>>7),61|t))&0xffffffff)^t
        return ((t^(t>>14))&0xffffffff)/4294967296
    return r
def run(k,noise,win,mags,scale=1.0,seed=7):
    r=mul(seed)
    def g():
        u=0;v=0
        while not u:u=r()
        while not v:v=r()
        return math.sqrt(-2*math.log(u))*math.cos(2*math.pi*v)
    x=[10+2*math.sin(i/14)+g()*noise*0.6 for i in range(240)]
    pos=[40,75,105,135,165,195,220,232]
    for j,p in enumerate(pos): x[p]+=mags[j]*(-1 if j%2 else 1)*scale
    an=set(pos); tp=fp=0
    fl=[]
    for i,v in enumerate(x):
        if i<win: fl.append(False);continue
        s=x[i-win:i];m=sum(s)/win;sd=math.sqrt(sum((b-m)**2 for b in s)/win) or 1
        fl.append(abs(v-m)/sd>k)
    for i,f in enumerate(fl):
        if f and i in an: tp+=1
        elif f: fp+=1
    return tp,fp,len(an)-tp
mags=[float(v) for v in sys.argv[1].split(',')] if len(sys.argv)>1 else [6.5,5.2,7,5,6.8,5.4,7.5,5.1]
for k in (1.5,3,5):
  for n in (1.0,):
    for w in (30,):
      print(k,n,w,run(k,n,w,mags))
print('noise2',run(3,2,30,mags),'win10',run(3,1,10,mags),'win60',run(3,1,60,mags))
