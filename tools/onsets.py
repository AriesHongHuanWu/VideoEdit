import sys, json, numpy as np, librosa
y, sr = librosa.load(sys.argv[1], sr=44100, mono=True)
a0, a1 = float(sys.argv[2]), float(sys.argv[3])
hop=256
H, P = librosa.effects.hpss(y, margin=(1.0, 3.0))
def band_onset(sig, lo, hi):
    Sx = np.abs(librosa.stft(sig, n_fft=2048, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    m=(f>=lo)&(f<hi)
    return librosa.onset.onset_strength(S=librosa.amplitude_to_db(Sx[m]), sr=sr, hop_length=hop, lag=1, max_size=1)
kick = band_onset(y, 25, 120); snare = band_onset(P, 1500, 8000); vox = band_onset(H, 250, 4000)
t = librosa.frames_to_time(np.arange(len(kick)), sr=sr, hop_length=hop)
def picks(env, delta):
    e=env/np.percentile(env,99)
    pk=librosa.util.peak_pick(e, pre_max=6, post_max=6, pre_avg=20, post_avg=20, delta=delta, wait=8)
    return [(float(t[p]), float(e[p])) for p in pk if a0<=t[p]<a1]
P0=5.78; period=0.363616
def grid(x): return (x-P0)/period
for name, env, dl in [('KICK/808',kick,0.25),('SNARE/CLAP',snare,0.25),('VOCAL',vox,0.2)]:
    print('==',name)
    print(' '.join(f"{tt:.2f}({s:.1f}|b{grid(tt):.1f})" for tt,s in picks(env, dl)))
