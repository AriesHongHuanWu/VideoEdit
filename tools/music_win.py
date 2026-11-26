import sys, json, numpy as np, librosa
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
hop=128
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=2048)
t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
an=json.load(open(sys.argv[2])); beats=np.array(an['beats'])
wins=[(0,7.5),(13.5,19.5),(25.5,31.5),(55.5,61.5)]
D = librosa.amplitude_to_db(S, ref=np.max)
fig, axs = plt.subplots(len(wins),1, figsize=(24, 4.2*len(wins)))
sub = S[(f>=25)&(f<90)].mean(0); sub/=np.percentile(sub,95)
harm = S[(f>=300)&(f<3000)].mean(0); harm/=np.percentile(harm,95)
hi = S[(f>=5000)].mean(0); hi/=np.percentile(hi,95)
for ax,(a,b) in zip(axs,wins):
    k=(t>=a)&(t<b)
    ax.imshow(D[:300][:,k], origin='lower', aspect='auto', extent=[a,b,0,f[300]], cmap='magma', vmin=-75, vmax=0)
    ax2=ax.twinx(); ax2.plot(t[k], sub[k], 'c', lw=1.2, label='sub'); ax2.plot(t[k], harm[k], 'lime', lw=0.8, label='harm'); ax2.plot(t[k], hi[k], 'w', lw=0.6, label='hi'); ax2.set_ylim(0,2.2); ax2.legend(loc='upper right',fontsize=7)
    for i,bt in enumerate(beats):
        if a<=bt<b: ax.axvline(bt, color='r' if i%16==0 else ('y' if i%4==0 else 'w'), lw=1.4 if i%16==0 else 0.6, alpha=0.8)
    ax.set_xticks(np.arange(a,b,0.25)); ax.tick_params(labelsize=6)
plt.tight_layout(); plt.savefig(sys.argv[3], dpi=60)
