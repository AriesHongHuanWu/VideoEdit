import sys, json, numpy as np, librosa
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
hop=64
S = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=4096)
t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
sub = S[(f>=25)&(f<100)].mean(0); sub/=np.percentile(sub,95)
harm = S[(f>=300)&(f<3000)].mean(0); harm/=np.percentile(harm,95)
an=json.load(open(sys.argv[2])); beats=np.array(an['beats'])
# 808 onsets: positive jumps in sub
d = np.diff(np.convolve(sub, np.ones(5)/5, mode='same'), prepend=0)
peaks = librosa.util.peak_pick(d, pre_max=40, post_max=40, pre_avg=40, post_avg=40, delta=0.02, wait=60)
rows=[]
for p in peaks:
    tp=t[p]
    # gap: time before tp where sub < 0.12
    k=p-3; g=0
    while k>0 and sub[k]<0.12: g+=hop/sr; k-=1
    bi = (tp-beats[0])/np.median(np.diff(beats))
    rows.append((tp,g,bi, float(sub[p:p+int(0.25*sr/hop)].mean()), float(harm[p:p+int(1.45*sr/hop)].mean())))
print(" t      gap   beatIdx  impact  harmAfter")
for r in rows:
    if r[1] > 0.25: print(f"{r[0]:6.2f}  {r[1]:4.2f}  {r[2]:6.2f}  {r[3]:5.2f}  {r[4]:5.2f}")
