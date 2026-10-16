import json, csv, math, sys
from scipy.optimize import brentq
root=sys.argv[1]
PS=72.67e-9; ANCHOR=-math.log(0.9992)
core={ (int(r['width']),r['adder']):r for r in csv.DictReader(open(f"{root}/results/study.csv"))}
sysr={ (r['width'],r['adder']):r for r in json.load(open(f"{root}/results/rf_system.json")) if r['what']=='system'}
rfr={ (r['width'],r['adder']):r for r in json.load(open(f"{root}/results/rf_system.json")) if r['what']=='rf'}
pipe={ (r['width'],r['adder']):r for r in json.load(open(f"{root}/results/rf_system_pipelined.json"))}
comp={ (r['width'],r['adder']):r for r in json.load(open(f"{root}/results/depth_compliant.json"))}
pts=[(1,'ripple'),(2,'ripple'),(4,'ripple'),(8,'ripple'),(16,'ripple'),(32,'ripple'),(8,'prefix'),(16,'prefix'),(32,'prefix')]
print("# Table: register file and integrated system")
print("| W | adder | T_RF | depth_RF | T_core | T_sys | T_sys/T_sys(W=1) | depth_sys | delay_sys (us) | f_max,sys (Hz) | E/instr 1 kHz (uJ) | S_sys | T_sys,c |")
designsA={}; designsC={}
for w,a in pts:
    c=core[(w,a)]; s=sysr[(w,a)]; rf=rfr[(w,a)]; p=pipe[(w,a)]
    cpi=float(c['cpi_geomean']); T=s['transistors']; dl=s['delay_us']; fm=1e6/dl
    E=PS*T*cpi/1000*1e6
    print(f"| {w} | {a} | {rf['transistors']:,} | {rf['depth']} | {c['transistors']} | {T:,} | {T/sysr[(1,'ripple')]['transistors']:.2f} | {s['depth']} | {dl} | {fm:,.0f} | {E:.2f} | {p['S']} | {p['T_c']:,} |")
    designsA[f"W={w} {a}"]=dict(T=T,cpi=cpi,thr_1k=1000/cpi,thr_fmax=fm/cpi)
    designsC[f"W={w} {a}"]=dict(T=p['T_c'],cpi=cpi*p['S'],thr_1k=1000/(cpi*p['S']),thr_fmax=5847.3/(cpi*p['S']))
def lm(x,d,key,pa):
    v=-x*d['T']+math.log(d[key])
    return v-math.log(d['T']) if pa else v
def env(designs,key,pa):
    seq=[]
    for i in range(20001):
        x=1e-8*(5e-3/1e-8)**(i/20000)
        b=max(designs,key=lambda k:lm(x,designs[k],key,pa))
        if not seq or seq[-1][0]!=b: seq.append((b,x))
    out=[(seq[0][0],0)]
    for j in range(1,len(seq)):
        a,b=designs[seq[j-1][0]],designs[seq[j][0]]
        f=lambda x: lm(x,a,key,pa)-lm(x,b,key,pa)
        lo,hi=seq[j][1]/1.01,seq[j][1]*1.01
        out.append((seq[j][0], brentq(f,lo,hi) if f(lo)*f(hi)<0 else seq[j][1]))
    return out
print("\n# Ladders with the register file on the die")
for name,ds in (("delay budget",designsA),("cascade",designsC)):
    for clk,key in (("1 kHz","thr_1k"),("f_max/f_c","thr_fmax")):
        for m,pa in (("per die",False),("per area",True)):
            e=env(ds,key,pa)
            print(f"{name}, {clk}, {m}: "+" -> ".join(f"{n} ({x*1e6:.0f})" for n,x in e)+f"; margin x{ANCHOR/e[-1][1]:.2f}" if e[-1][1]>0 else name)
print("\n# energy ratios with RF, fixed clock / iso-throughput")
s1=designsA["W=1 ripple"]
for k in ("W=32 ripple","W=32 prefix","W=16 prefix"):
    d=designsA[k]; print(k, "fixed-clock ratio %.2f"%(s1['T']*s1['cpi']/(d['T']*d['cpi'])), "T ratio %.3f"%(d['T']/s1['T']))
c1=designsC["W=1 ripple"]
for k in ("W=32 prefix","W=16 prefix"):
    d=designsC[k]; print("cascade",k,"fixed-clock ratio %.2f"%(c1['T']*c1['cpi']/(d['T']*d['cpi'])),"thr ratio %.2f"%(d['thr_fmax']/c1['thr_fmax']),"T ratio %.2f"%(d['T']/c1['T']))
print("\n# die yield of the integrated W=1 system")
T1=designsA["W=1 ripple"]['T']
print("at 800 ppm:", math.exp(-ANCHOR*T1), "; d for 50%% die yield: %.1f ppm; for 10%%: %.1f ppm"%(math.log(2)/T1*1e6, math.log(10)/T1*1e6))
print("core-only W=1 at 800 ppm:", math.exp(-ANCHOR*10474))
