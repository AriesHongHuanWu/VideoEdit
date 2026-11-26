import sys, json, numpy as np, librosa
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
hop=64
S = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=4096)
t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
sub = S[(f>=25)&(f<100)].mean(0); sub/=np.percentile(sub,95)
harm = S[(f>=300)&(f<3000)].mean(0); harm/=np.percentile(harm,95)
full = S.mean(0); full/=np.percentile(full,95)
an=json.load(open(sys.argv[2])); beats=np.array(an['beats']); ibi=np.median(np.diff(beats))
print('sub percentiles', np.percentile(sub,[1,5,10,25,50]))
low = sub < 0.10
i=0; n=len(sub); out=[]
while i<n:
    if low[i]:
        j=i
        while j<n and low[j]: j+=1
        gap=(j-i)*hop/sr
        if gap>0.2 and j<n:
            tp=t[j]; bi=(tp-beats[0])/ibi
            out.append((t[i], tp, gap, bi, float(sub[j:j+int(0.3*sr/hop)].max()), float(harm[j:j+int(2.9*sr/hop)].mean()), float(full[i:j].mean())))
        i=j
    else: i+=1
print(" gapStart reentry  gap   beatIdx  impactMax harmAfter fullDuringGap")
for r in out: print(f"{r[0]:7.2f} {r[1]:7.2f}  {r[2]:4.2f}  {r[3]:7.2f}  {r[4]:5.2f}   {r[5]:5.2f}  {r[6]:5.2f}")
