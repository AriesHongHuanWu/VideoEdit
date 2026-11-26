import sys, json, numpy as np, librosa, soundfile as sf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
path, out = sys.argv[1], sys.argv[2]
y, sr = librosa.load(path, sr=22050, mono=True)
dur = len(y)/sr
hop = 256
oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=hop, units='time', tightness=200)
tempo = float(np.atleast_1d(tempo)[0])
# alternative tempo estimates
tg = librosa.feature.tempogram(onset_envelope=oenv, sr=sr, hop_length=hop)
ac_tempo = librosa.feature.tempo(onset_envelope=oenv, sr=sr, hop_length=hop, aggregate=None)
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
def band(lo, hi):
    m = (freqs>=lo)&(freqs<hi); return S[m].mean(0)
low = band(20,150); mid = band(150,2000); high = band(2000,11000)
rms = librosa.feature.rms(S=S)[0]
t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
def smooth(x, w=40):
    k = np.ones(w)/w; return np.convolve(x, k, mode='same')
# per-beat stats
res = dict(duration=dur, tempo=tempo, beats=[float(b) for b in beats])
# downbeat guess: phase that maximises low-band energy on beat 1 of 4
bi = librosa.time_to_frames(beats, sr=sr, hop_length=hop)
lb = low[np.clip(bi,0,len(low)-1)]
ph_scores = [float(lb[p::4].mean()) for p in range(4)]
res['downbeat_phase_scores'] = ph_scores
# spectral centroid
cent = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
# segment boundaries via agglomerative on chroma+mfcc
mf = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
ch = librosa.feature.chroma_stft(S=S**2, sr=sr)
feat = np.vstack([librosa.util.normalize(mf,axis=1), ch])
bsync = librosa.util.sync(feat, bi, aggregate=np.median)
bounds = librosa.segment.agglomerative(bsync, 10)
bt = [float(beats[min(b, len(beats)-1)]) for b in bounds]
res['segment_bounds'] = bt
json.dump(res, open(out+'.json','w'), indent=1)
fig, ax = plt.subplots(5,1, figsize=(22,13), sharex=True)
D = librosa.amplitude_to_db(S, ref=np.max)
ax[0].imshow(D[:400], origin='lower', aspect='auto', extent=[0,dur,0,freqs[400]], cmap='magma', vmin=-70, vmax=0)
ax[0].set_ylabel('Hz (0-4.3k)')
ax[1].plot(t, smooth(low)/smooth(low).max(), label='low 20-150'); ax[1].plot(t, smooth(mid)/smooth(mid).max(), label='mid'); ax[1].plot(t, smooth(high)/smooth(high).max(), label='high'); ax[1].legend(loc='upper left')
ax[2].plot(t, smooth(rms,20)); ax[2].set_ylabel('rms')
ax[3].plot(t, oenv, lw=0.5); ax[3].set_ylabel('onset')
for b in beats: ax[3].axvline(b, color='r', lw=0.3)
ax[4].plot(t, smooth(cent,40)); ax[4].set_ylabel('centroid')
for a in ax:
    for b in bt: a.axvline(b, color='c', lw=1.2, ls='--')
    a.grid(alpha=0.3)
ax[4].set_xticks(np.arange(0, dur, 2))
plt.tight_layout(); plt.savefig(out+'.png', dpi=70)
print('tempo', tempo, 'n beats', len(beats), 'ac tempo median', float(np.median(ac_tempo)))
print('downbeat phase scores', ph_scores)
print('segments', [round(x,2) for x in bt])
print('first beats', [round(b,3) for b in beats[:12]])
ibi = np.diff(beats); print('IBI median', float(np.median(ibi)), 'std', float(ibi.std()))
