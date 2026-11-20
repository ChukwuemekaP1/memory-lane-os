"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Mic, Pause, Play, Square, Trash2, UploadCloud } from "lucide-react";

import { AnimatePresence, motion } from "@/components/ui/motion";

const BAR_COUNT = 28;

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function pickSupportedAudioMime(): { mime: string; ext: string } {
  if (typeof MediaRecorder === "undefined") {
    return { mime: "audio/webm", ext: "webm" };
  }
  const candidates = [
    { mime: "audio/webm;codecs=opus", ext: "webm" },
    { mime: "audio/webm", ext: "webm" },
    { mime: "audio/ogg;codecs=opus", ext: "ogg" },
    { mime: "audio/mp4", ext: "m4a" },
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c.mime)) return c;
  }
  return { mime: "audio/webm", ext: "webm" };
}

export function VoiceRecorder({
  file,
  onChange,
  disabled = false,
}: {
  file: File | null;
  onChange: (next: File | null) => void;
  disabled?: boolean;
}) {
  const [state, setState] = useState<"idle" | "recording" | "paused" | "recorded">(
    file ? "recorded" : "idle",
  );
  const [elapsed, setElapsed] = useState(0);
  const [bars, setBars] = useState<number[]>(() => Array(BAR_COUNT).fill(14));
  const [micError, setMicError] = useState<string | null>(null);

  // Playback preview state
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [playProgress, setPlayProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      setPlaying(false);
      setPlayProgress(0);
      if (state === "recorded") setState("idle");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setState("recorded");
    return () => URL.revokeObjectURL(url);
  }, [file]); // eslint-disable-line react-hooks/exhaustive-deps

  function cleanupAudioNodes() {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    if (audioCtxRef.current) {
      void audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }

  useEffect(() => cleanupAudioNodes, []);

  function startWaveformLoop() {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      if (!analyserRef.current) return;
      analyserRef.current.getByteFrequencyData(data);
      const step = Math.max(1, Math.floor(data.length / BAR_COUNT));
      const next: number[] = [];
      for (let i = 0; i < BAR_COUNT; i++) {
        const val = data[i * step] ?? 0;
        next.push(Math.max(12, Math.min(100, Math.round((val / 255) * 100))));
      }
      setBars(next);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }

  async function startRecording() {
    setMicError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError("Your browser does not support live microphone recording. Upload an audio file below instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const { mime, ext } = pickSupportedAudioMime();
      const recorder = new MediaRecorder(stream, MediaRecorder.isTypeSupported(mime) ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = () => {
        const cleanMime = mime.split(";")[0] || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: cleanMime });
        if (blob.size > 0) {
          const recordedFile = new File([blob], `voice-note-${Date.now()}.${ext}`, {
            type: cleanMime,
          });
          onChange(recordedFile);
        }
        cleanupAudioNodes();
      };

      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 128;
      src.connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;

      recorderRef.current = recorder;
      recorder.start(250);
      setElapsed(0);
      setState("recording");
      startWaveformLoop();
      timerRef.current = window.setInterval(() => {
        setElapsed((sec) => sec + 1);
      }, 1000);
    } catch {
      cleanupAudioNodes();
      setMicError("Microphone permission was denied. Allow mic access or upload an audio file below.");
    }
  }

  function togglePauseRecording() {
    const rec = recorderRef.current;
    if (!rec) return;
    if (rec.state === "recording") {
      rec.pause();
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      setState("paused");
    } else if (rec.state === "paused") {
      rec.resume();
      setState("recording");
      startWaveformLoop();
      timerRef.current = window.setInterval(() => setElapsed((sec) => sec + 1), 1000);
    }
  }

  function finishRecording() {
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      setDuration(elapsed);
      rec.stop();
    }
  }

  function cancelRecording() {
    const rec = recorderRef.current;
    chunksRef.current = [];
    if (rec && rec.state !== "inactive") {
      rec.onstop = () => cleanupAudioNodes();
      rec.stop();
    } else {
      cleanupAudioNodes();
    }
    setElapsed(0);
    setBars(Array(BAR_COUNT).fill(14));
    onChange(null);
    setState("idle");
  }

  function togglePreviewPlay() {
    const el = audioElRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
      setPlaying(false);
    } else {
      void el.play();
      setPlaying(true);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="glass-panel rounded-2xl p-4 sm:p-5">
        <AnimatePresence mode="wait">
          {state === "idle" && (
            <motion.div
              key="idle"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="flex flex-col items-center gap-3 py-3 text-center"
            >
              <motion.button
                type="button"
                disabled={disabled}
                whileHover={{ scale: 1.06 }}
                whileTap={{ scale: 0.92 }}
                onClick={startRecording}
                aria-label="Start recording voice note"
                className="relative flex h-16 w-16 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] shadow-lg ring-8 ring-[var(--sage)]/70 transition-shadow hover:shadow-xl disabled:opacity-50"
              >
                <Mic className="h-7 w-7" />
              </motion.button>
              <div>
                <p className="text-sm font-semibold text-[var(--foreground)]">
                  Tap to record a voice note
                </p>
                <p className="text-xs text-[var(--muted-foreground)]">
                  Speak naturally — we&apos;ll save your voice and can transcribe it in AI Studio.
                </p>
              </div>
            </motion.div>
          )}

          {(state === "recording" || state === "paused") && (
            <motion.div
              key="recording"
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              className="flex flex-col gap-4"
            >
              {/* WhatsApp-style Live Bar */}
              <div className="flex items-center gap-3 rounded-full bg-white/80 px-4 py-3 shadow-inner ring-1 ring-[var(--border)]">
                <span className="relative flex h-3 w-3 shrink-0">
                  {state === "recording" && (
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
                  )}
                  <span
                    className={`relative inline-flex h-3 w-3 rounded-full ${
                      state === "recording" ? "bg-red-600" : "bg-amber-500"
                    }`}
                  />
                </span>
                <span className="w-11 shrink-0 font-mono text-sm font-semibold tabular-nums text-[var(--foreground)]">
                  {formatTimer(elapsed)}
                </span>
                <div className="flex h-8 flex-1 items-center justify-between gap-[2px] overflow-hidden">
                  {bars.map((height, idx) => (
                    <motion.span
                      key={idx}
                      animate={{ height: `${state === "paused" ? 16 : height}%` }}
                      transition={{ duration: 0.09, ease: "easeOut" }}
                      className="w-1 rounded-full bg-[var(--primary)]/80"
                    />
                  ))}
                </div>
              </div>

              {/* WhatsApp-style Controls: Delete | Pause/Resume | Done */}
              <div className="flex items-center justify-between px-2">
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.88 }}
                  onClick={cancelRecording}
                  aria-label="Discard recording"
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-red-50 text-red-700 hover:bg-red-100"
                >
                  <Trash2 className="h-5 w-5" />
                </motion.button>

                <motion.button
                  type="button"
                  whileTap={{ scale: 0.9 }}
                  onClick={togglePauseRecording}
                  aria-label={state === "recording" ? "Pause recording" : "Resume recording"}
                  className="glass-pill flex h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold"
                >
                  {state === "recording" ? (
                    <>
                      <Pause className="h-4 w-4 text-red-600" />
                      Pause
                    </>
                  ) : (
                    <>
                      <Mic className="h-4 w-4 text-[var(--primary)]" />
                      Resume
                    </>
                  )}
                </motion.button>

                <motion.button
                  type="button"
                  whileTap={{ scale: 0.9 }}
                  onClick={finishRecording}
                  aria-label="Finish and attach voice note"
                  className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] shadow-md hover:brightness-110"
                >
                  <Square className="h-4 w-4 fill-current" />
                </motion.button>
              </div>
            </motion.div>
          )}

          {state === "recorded" && file && previewUrl && (
            <motion.div
              key="recorded"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="flex items-center gap-3 rounded-2xl bg-[var(--sage)]/55 px-4 py-3"
            >
              <audio
                ref={audioElRef}
                src={previewUrl}
                onLoadedMetadata={(e) => {
                  const d = e.currentTarget.duration;
                  if (Number.isFinite(d) && d > 0) setDuration(Math.round(d));
                }}
                onTimeUpdate={(e) => {
                  const d = e.currentTarget.duration || duration || 1;
                  setPlayProgress(Math.min(100, (e.currentTarget.currentTime / d) * 100));
                }}
                onEnded={() => {
                  setPlaying(false);
                  setPlayProgress(0);
                }}
                className="hidden"
              />
              <motion.button
                type="button"
                whileTap={{ scale: 0.9 }}
                onClick={togglePreviewPlay}
                aria-label={playing ? "Pause voice note" : "Play voice note"}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm"
              >
                {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 translate-x-0.5" />}
              </motion.button>

              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="inline-flex items-center gap-1 font-semibold text-[var(--primary)]">
                    <Check className="h-3.5 w-3.5" />
                    Voice note ready
                  </span>
                  <span className="font-mono text-[var(--muted-foreground)]">
                    {formatTimer(duration || elapsed)} · {(file.size / 1024).toFixed(0)} KB
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-white/80">
                  <div
                    className="h-full rounded-full bg-[var(--primary)] transition-all duration-100"
                    style={{ width: `${playProgress}%` }}
                  />
                </div>
              </div>

              {!disabled && (
                <button
                  type="button"
                  onClick={cancelRecording}
                  aria-label="Delete voice note"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full hover:bg-black/5"
                >
                  <Trash2 className="h-4 w-4 text-red-700" />
                </button>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {micError && (
        <p role="alert" className="rounded-[var(--radius)] bg-amber-50 px-3.5 py-2.5 text-xs text-amber-950">
          {micError}
        </p>
      )}

      {state === "idle" && (
        <label className="glass-pill flex cursor-pointer items-center justify-center gap-2 rounded-full px-4 py-2 text-xs font-medium text-[var(--muted-foreground)]">
          <UploadCloud className="h-3.5 w-3.5" />
          <span>Or upload an existing audio file (MP3, M4A, WAV, OGG)</span>
          <input
            type="file"
            accept="audio/*"
            disabled={disabled}
            onChange={(e) => {
              const picked = e.target.files?.[0] ?? null;
              if (picked) onChange(picked);
            }}
            className="hidden"
          />
        </label>
      )}
    </div>
  );
}
