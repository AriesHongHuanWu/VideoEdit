import sys, json, numpy as np, librosa
y, sr = librosa.load(sys.argv[1], sr=44100, mono=True)
hop=128
H, P = librosa.effects.hpss(y, margin=(1.0, 3.0))
oenv = librosa.onset.onset_strength(y=P, sr=sr, hop_length=hop)
t = librosa.frames_to_time(np.arange(len(oenv)), sr=sr, hop_length=hop)
best=None
for per in np.arange(0.3620, 0.3652, 0.00002):
    step = per/2  # 16th grid
    for ph in np.arange(0, step, 0.002):
        g = np.arange(ph, t[-1], step)
        idx = np.clip(np.round(g*sr/hop).astype(int), 0, len(oenv)-1)
        sc = oenv[idx].mean()
        if best is None or sc>best[0]: best=(sc, per, ph)
sc, per, ph = best
print('best period', round(per,5), 'BPM', round(60/per,3), '16th phase', round(ph,4), 'score', round(sc,3))
# which of the two 16th phases is the 8th beat: compare onset strength at ph vs ph+per/2
def strength(phase):
    g=np.arange(phase, t[-1], per); idx=np.clip(np.round(g*sr/hop).astype(int),0,len(oenv)-1); return oenv[idx].mean()
s0, s1 = strength(ph), strength(ph+per/2)
beat_phase = ph if s0>=s1 else ph+per/2
print('8th-beat phase', round(beat_phase,4), 'strengths', round(s0,3), round(s1,3))
# kick (sub) strength by beat index mod 8 to find bar downbeat
Sx=np.abs(librosa.stft(y,n_fft=4096,hop_length=hop)); f=librosa.fft_frequencies(sr=sr,n_fft=4096)
subo = librosa.onset.onset_strength(S=librosa.amplitude_to_db(Sx[(f>=25)&(f<120)]), sr=sr, hop_length=hop)
hiS = librosa.onset.onset_strength(S=librosa.amplitude_to_db(np.abs(librosa.stft(P,n_fft=4096,hop_length=hop))[(f>=1500)&(f<6000)]), sr=sr, hop_length=hop)
g=np.arange(beat_phase, t[-1], per); idx=np.clip(np.round(g*sr/hop).astype(int),0,len(oenv)-1)
for name,env in [('sub',subo),('snareband',hiS)]:
    v=env[idx]; print(name, 'mean by beat mod 8:', [round(float(v[k::8].mean()),2) for k in range(8)])
json.dump(dict(period=per, beat_phase=beat_phase), open(sys.argv[2],'w'))
