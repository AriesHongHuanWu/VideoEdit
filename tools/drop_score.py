import sys, json, numpy as np, librosa
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
hop=128
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=2048)
t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
sub = S[(f>=25)&(f<90)].mean(0); sub/=np.percentile(sub,95)
rms = librosa.feature.rms(S=S)[0]; rms/=np.percentile(rms,95)
hi = S[(f>=4000)].mean(0); hi/=np.percentile(hi,95)
harm = S[(f>=300)&(f<3000)].mean(0); harm/=np.percentile(harm,95)
oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
an=json.load(open(sys.argv[2])); beats=np.array(an['beats'])
starts = beats[0::16]
def m(x,a,b): k=(t>=a)&(t<b); return float(x[k].mean()) if k.any() else 0
print("phrase  dipSub(-0.75..0)  dipLen  impactSub  impactRMS  buildHarm  buildHi  postRMS  postOnset")
for p in starts:
    pre = m(sub, p-0.75, p-0.03)
    # dip length: contiguous time before p with sub<0.15
    k = np.where((t<p-0.02)&(t>p-2.5))[0][::-1]; L=0
    for i in k:
        if sub[i] < 0.15: L += hop/sr
        else: break
    imp = m(sub, p, p+0.30); impr = m(rms, p, p+0.30)
    bh = m(harm, p-2.9, p) - m(harm, p-5.8, p-2.9); bhi = m(hi, p-2.9, p) - m(hi, p-5.8, p-2.9)
    post = m(rms, p, p+5.8); pon = m(oenv, p, p+5.8)
    print(f"{p:6.2f}   {pre:6.3f}   {L:5.2f}   {imp:6.3f}   {impr:6.3f}   {bh:+6.3f}   {bhi:+6.3f}   {post:6.3f}  {pon:6.3f}")
