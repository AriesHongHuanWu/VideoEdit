import sys, json, numpy as np, librosa
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
path, out = sys.argv[1], sys.argv[2]
y, sr = librosa.load(path, sr=22050, mono=True)
hop=256
H, P = librosa.effects.hpss(y)
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)); Sh=np.abs(librosa.stft(H,n_fft=2048,hop_length=hop)); Sp=np.abs(librosa.stft(P,n_fft=2048,hop_length=hop))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048); t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
an = json.load(open(sys.argv[3]))
beats = np.array(an['beats'])
def sm(x,w=10): return np.convolve(x, np.ones(w)/w, mode='same')
low = S[(freqs>=20)&(freqs<120)].mean(0); sub= S[(freqs>=20)&(freqs<60)].mean(0)
harm = Sh[(freqs>=200)&(freqs<3000)].mean(0); perc = Sp[(freqs>=2000)].mean(0)
D = librosa.amplitude_to_db(S, ref=np.max)
n=4; span=np.ceil(t[-1]/n)
fig, axs = plt.subplots(n*2,1, figsize=(26, 5*n), gridspec_kw={'height_ratios':[2,1]*n})
for k in range(n):
    a0, a1 = k*span, min((k+1)*span, t[-1])
    m = (t>=a0)&(t<a1)
    ax=axs[2*k]; ax.imshow(D[:, m][:600], origin='lower', aspect='auto', extent=[a0,a1,0,freqs[600]], cmap='magma', vmin=-70, vmax=0)
    for i,b in enumerate(beats):
        if a0<=b<a1: ax.axvline(b, color='w', lw=0.4 if i%4 else 1.0, alpha=0.6)
    ax.set_xticks(np.arange(np.floor(a0), a1, 0.5)); ax.tick_params(labelsize=7)
    ax2=axs[2*k+1]
    for arr,lab in [(low,'low<120'),(sub,'sub<60'),(harm,'harm 200-3k'),(perc,'perc>2k')]:
        v=sm(arr)[m]; ax2.plot(t[m], v/np.percentile(sm(arr),99), label=lab, lw=0.9)
    ax2.set_xlim(a0,a1); ax2.set_xticks(np.arange(np.floor(a0), a1, 0.5)); ax2.tick_params(labelsize=7); ax2.grid(alpha=0.3); ax2.legend(loc='upper right', fontsize=7)
plt.tight_layout(); plt.savefig(out, dpi=55)
# per-bar table (bar = 4 beats)
rows=[]
for i in range(0, len(beats)-4, 4):
    a, b = beats[i], beats[i+4]
    m=(t>=a)&(t<b)
    rows.append((round(a,2), round(float(low[m].mean()),2), round(float(sub[m].mean()),2), round(float(harm[m].mean()),3), round(float(perc[m].mean()),3)))
for r in rows: print(r)
