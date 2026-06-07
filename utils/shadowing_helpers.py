
import librosa
import torch
import whisper
import fugashi
from faster_whisper import WhisperModel
import numpy as np
from fastdtw import fastdtw
from scipy.spatial.distance import euclidean
import matplotlib.pyplot as plt
from yt_dlp import YoutubeDL

model = WhisperModel("medium", device='cuda' if torch.cuda.is_available() else 'cpu', compute_type="float16" if torch.cuda.is_available() else "int8")
tagger = fugashi.Tagger()

def transcribe_audio(file):
    # Transcribe the audio
    seg, _ = model.transcribe(file, language='ja')
    text = ''.join([s.text for s in seg])
    # Convert the transcription to katakana using fugashi
    words = convert_to_katakana(text)
    return words

def convert_to_katakana(text):
    words = tagger(text)
    s = [(word.surface, word.feature.kana) for word in words]
    s = [(surface, kana) for surface, kana in s if kana != '*' and kana != '']
    return s

def get_caption_error(reference, wrong_indices):
    indices = [0]
    result = []

    for ref_word, ref_kana in reference:
        last_index = indices[-1]
        indices.append(last_index + len(ref_kana))
        word_start = indices[-2]
        word_end = indices[-1]

        # A word is "wrong" if any error index falls within its character range
        has_error = any(word_start <= idx < word_end for idx in wrong_indices)
        result.append((ref_word, not has_error))

    return result


def calculate_cer(reference, target):
    ref_chars = list(''.join([kana for _, kana in reference]))
    tgt_chars = list(''.join([kana for _, kana in target]))

    # Build DP table
    d = [[0] * (len(tgt_chars) + 1) for _ in range(len(ref_chars) + 1)]
    for i in range(len(ref_chars) + 1): d[i][0] = i
    for j in range(len(tgt_chars) + 1): d[0][j] = j

    for i in range(1, len(ref_chars) + 1):
        for j in range(1, len(tgt_chars) + 1):
            if ref_chars[i-1] == tgt_chars[j-1]:
                d[i][j] = d[i-1][j-1]
            else:
                d[i][j] = 1 + min(d[i-1][j], d[i][j-1], d[i-1][j-1])

    # Traceback to find only the indices involved in actual edits
    wrong_indices = []
    i, j = len(ref_chars), len(tgt_chars)
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_chars[i-1] == tgt_chars[j-1]:
            i -= 1; j -= 1  # match — no error
        elif i > 0 and j > 0 and d[i][j] == d[i-1][j-1] + 1:
            wrong_indices.append(i - 1)  # substitution
            i -= 1; j -= 1
        elif j > 0 and d[i][j] == d[i][j-1] + 1:
            j -= 1  # insertion in target — no ref index to record
        else:
            wrong_indices.append(i - 1)  # deletion
            i -= 1

    cer = d[len(ref_chars)][len(tgt_chars)] / len(ref_chars)
    return cer, wrong_indices

def analyze_pitch_accent(ref_audio_path, target_audio_path, sr=22050,
                         start_time=0.0, end_time=None):
    f0_ref, sr_ref = extract_pitch(ref_audio_path, sr, start_time, end_time)
    f0_target, sr_target = extract_pitch(target_audio_path, sr, 0.0, None)

    normalized_ref    = normalize_pitch(f0_ref)
    normalized_target = normalize_pitch(f0_target)

    comparison = compare_pitch(normalized_ref, normalized_target)
    score = score_accent(comparison["normalized_distance"])

    fig = plot_comparison(normalized_ref, normalized_target, comparison["path"])

    return {
        "comparison": comparison,
        "score": score,
        "figure": fig,
        "normalized_ref": normalized_ref,
        "normalized_target": normalized_target,
    }

def extract_pitch(audio_path: str, sr: int = 22050, start_time: float = 0.0, end_time: float = None) -> (np.ndarray, int):
    y, sr = librosa.load(audio_path, sr=sr)
    if end_time is not None:
        y = y[int(start_time * sr):int(end_time * sr)]

    # pyin is more accurate than yin for voiced/unvoiced detection
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y,
        fmin=librosa.note_to_hz('C2'),   # ~65 Hz  — lowest expected pitch
        fmax=librosa.note_to_hz('C7'),   # ~2093 Hz — highest expected pitch
        sr=sr,
        frame_length=2048,
        hop_length=256,
    )

    # pyin returns NaN for unvoiced frames — replace with 0
    # f0 = np.nan_to_num(f0, nan=0.0)

    return f0, sr

def normalize_pitch(f0: np.ndarray) -> np.ndarray:
    voiced = f0[f0 > 0]
    if len(voiced) == 0:
        return f0

    mean_hz = np.mean(voiced)

    # Convert to semitones relative to speaker's mean pitch
    # semitones = 12 * log2(f0 / reference)
    normalized = np.where(
        f0 > 0,
        12 * np.log2(f0 / mean_hz),   # voiced frames → semitone offset
        0.0                            # unvoiced frames → stay 0
    )
    return normalized

def compare_pitch(f0_ref: np.ndarray, f0_target: np.ndarray):
    f0_ref = f0_ref[f0_ref > 0]
    f0_target = f0_target[f0_target > 0]
    # Reshape to 2D — fastdtw expects (n_frames, n_features)
    ref    = f0_ref.reshape(-1, 1)
    target = f0_target.reshape(-1, 1)

    distance, path = fastdtw(ref, target, dist=euclidean)

    # Normalize by path length — longer sequences naturally accumulate more cost
    normalized_distance = distance / len(path)

    return {
        "distance": distance,
        "normalized_distance": normalized_distance,
        "path": path,           # list of (i, j) index pairs showing alignment
        "path_length": len(path),
    }

def score_accent(normalized_distance: float) -> dict:
    # Thresholds — tune these based on your data
    if normalized_distance < 0.5:
        grade, feedback = "Excellent", "Pitch accent closely matches the reference."
    elif normalized_distance < 1.5:
        grade, feedback = "Good", "Minor pitch deviations — mostly correct."
    elif normalized_distance < 3.0:
        grade, feedback = "Fair", "Noticeable accent differences — review high/low patterns."
    else:
        grade, feedback = "Poor", "Significant pitch mismatch — practice the accent pattern."
    
    score = max(0, 100 - (normalized_distance * 20))  # Example: 0.5 → 90, 1.5 → 70, 3.0 → 40

    return {"grade": grade, "feedback": feedback, "score": round(score, 4)}


def plot_comparison(f0_ref, f0_target, path):
    fig, axes = plt.subplots(3, 1, figsize=(12, 8))

    # Raw pitch curves
    axes[0].plot(f0_ref,    label="Reference", color="blue",   alpha=0.8)
    axes[0].plot(f0_target, label="Target",    color="orange", alpha=0.8)
    axes[0].set_title("Pitch Curves (normalized semitones)")
    axes[0].set_ylabel("Semitones")
    axes[0].legend()

    # DTW alignment path
    path_ref    = [p[0] for p in path]
    path_target = [p[1] for p in path]
    axes[1].plot(path_ref, path_target, color="green", linewidth=0.8)
    axes[1].set_title("DTW Alignment Path")
    axes[1].set_xlabel("Reference frame")
    axes[1].set_ylabel("Target frame")

    # Frame-by-frame difference after alignment
    diff = [f0_ref[p[0]] - f0_target[p[1]] for p in path]
    axes[2].fill_between(range(len(diff)), diff, alpha=0.5, color="red")
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].set_title("Pitch Difference After Alignment (semitones)")
    axes[2].set_ylabel("Δ semitones")

    return fig

def download_youtube_audio(youtube_url: str, output_path: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])