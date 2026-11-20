"use client";

import { useState } from "react";
import {
  Camera,
  Film,
  FileAudio,
  Lock,
  MessageSquareHeart,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";

import { SpaceCoverBand, SpaceLink, SpaceNav, useSpace } from "@/components/space-provider";
import { Button } from "@/components/ui/button";
import { AnimatedTabs, FadeInUp, GlassCard, SuccessCheckmark } from "@/components/ui/motion";
import { VoiceRecorder } from "@/components/voice-recorder";
import { ApiError, postContribution } from "@/lib/spaces";
import { uploadFile, type UploadStatus } from "@/lib/upload";

type Kind = "message" | "photo" | "video" | "audio";

export function ContributeForm({ spaceId }: { spaceId: string }) {
  const { space, token } = useSpace();
  const canPost = space.my_permissions.includes("post");
  const [kind, setKind] = useState<Kind>("message");
  const [body, setBody] = useState("");
  const [name, setName] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [isPrivate, setIsPrivate] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploads, setUploads] = useState<Record<string, UploadStatus>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ status: string; message: string } | null>(null);

  if (!canPost) {
    return (
      <div>
        <SpaceCoverBand spaceId={spaceId} />
        <main className="site-frame py-8">
          <SpaceNav spaceId={spaceId} active="/contribute" />
          <GlassCard className="mx-auto max-w-xl p-8 text-center">
            <p className="font-display text-2xl font-medium">Contributions are closed</p>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">
              This memory space is not accepting new submissions from your link right now.
            </p>
          </GlassCard>
        </main>
      </div>
    );
  }

  function handleFiles(incoming: FileList | File[]) {
    const list = [...incoming].slice(0, 10);
    setFiles(list);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (kind !== "message" && files.length === 0) {
      setError(
        kind === "audio"
          ? "Please tap the mic to record a voice note or upload an audio file first."
          : `Please attach at least one ${kind} file first.`,
      );
      return;
    }
    if (!anonymous && !name.trim() && space.my_role?.startsWith("guest")) {
      setError("Please add your name or choose to post anonymously.");
      return;
    }
    setSubmitting(true);
    try {
      const uploaded: string[] = [];
      for (const file of files) {
        const key = `${file.name}-${file.size}`;
        setUploads((current) => ({ ...current, [key]: { stage: "presigning" } }));
        const assetId = await uploadFile(spaceId, file, token, {
          onStatus: (status) => setUploads((current) => ({ ...current, [key]: status })),
        });
        uploaded.push(assetId);
      }
      const effectiveKind =
        kind === "audio" ? "audio" : kind === "photo" || kind === "video" ? "media" : "message";
      const created = await postContribution(
        spaceId,
        {
          kind: uploaded.length > 0 ? effectiveKind : "message",
          body: body.trim() || undefined,
          guest_name: anonymous ? undefined : name.trim() || undefined,
          is_anonymous: anonymous,
          is_private_to_owner: effectiveKind === "message" ? isPrivate : false,
          asset_ids: uploaded.length > 0 ? uploaded : undefined,
        },
        token,
      );
      setDone({
        status: created.status,
        message:
          created.status === "pending"
            ? `Thank you! Your memory was sent to ${space.space.title} and will appear once approved by the host.`
            : `Thank you! Your memory is now live in ${space.space.title}.`,
      });
      setBody("");
      setFiles([]);
      setUploads({});
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Something went wrong. Please retry.");
    } finally {
      setSubmitting(false);
    }
  }

  const needsFiles = kind !== "message";
  const acceptAttr =
    kind === "photo" ? "image/*" : kind === "video" ? "video/*" : kind === "audio" ? "audio/*" : "";

  return (
    <div className="pb-20">
      <SpaceCoverBand spaceId={spaceId} />

      <main className="site-frame py-8">
        <SpaceNav spaceId={spaceId} active="/contribute" />

        <FadeInUp className="mx-auto max-w-2xl">
          {done ? (
            <GlassCard className="flex flex-col items-center gap-4 p-10 text-center">
              <SuccessCheckmark />
              <h2 className="font-display text-3xl font-medium">Memory received</h2>
              <p className="max-w-md text-sm leading-relaxed text-[var(--muted-foreground)]">
                {done.message}
              </p>
              <div className="mt-2 flex flex-wrap justify-center gap-3">
                <Button type="button" onClick={() => setDone(null)}>
                  Submit another memory
                </Button>
                <SpaceLink
                  href={`/s/${spaceId}`}
                  className="glass-pill inline-flex min-h-[44px] items-center rounded-[var(--radius)] px-5 text-sm font-medium"
                >
                  View album
                </SpaceLink>
              </div>
            </GlassCard>
          ) : (
            <GlassCard className="flex flex-col gap-6 p-6 sm:p-8">
              <div>
                <p className="eyebrow text-[var(--bronze)]">No account required</p>
                <h2 className="mt-1 font-display text-3xl font-medium">Add your memory</h2>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                  Share a photo, video, voice note, or heartfelt message directly to this album.
                </p>
              </div>

              <AnimatedTabs
                layoutId="contribute-kind"
                value={kind}
                onChange={(next) => {
                  setKind(next);
                  setFiles([]);
                  setUploads({});
                }}
                items={[
                  { value: "message", label: "Message", icon: <MessageSquareHeart className="h-4 w-4" /> },
                  { value: "photo", label: "Photo", icon: <Camera className="h-4 w-4" /> },
                  { value: "video", label: "Video", icon: <Film className="h-4 w-4" /> },
                  { value: "audio", label: "Audio", icon: <FileAudio className="h-4 w-4" /> },
                ]}
              />

              <form onSubmit={submit} className="flex flex-col gap-4">
                {kind === "audio" && (
                  <VoiceRecorder
                    file={files[0] ?? null}
                    onChange={(recorded) => setFiles(recorded ? [recorded] : [])}
                    disabled={submitting}
                  />
                )}

                {(kind === "photo" || kind === "video") && (
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOver(false);
                      if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
                    }}
                    className={`relative flex flex-col items-center justify-center gap-2 rounded-[var(--radius)] border-2 border-dashed p-7 text-center transition-all ${
                      dragOver
                        ? "border-[var(--primary)] bg-[var(--sage)]/55 scale-[1.01]"
                        : "border-[var(--border)] bg-white/55 hover:border-[var(--ring)]"
                    }`}
                  >
                    <UploadCloud className="h-8 w-8 text-[var(--primary)]" />
                    <p className="text-sm font-medium">
                      Drag &amp; drop your {kind} here, or click to browse
                    </p>
                    <p className="text-xs text-[var(--muted-foreground)]">
                      {kind === "photo"
                        ? "JPG, PNG, WebP, HEIC (up to 25 MB)"
                        : "MP4, MOV, WebM"}
                    </p>
                    <input
                      type="file"
                      required={files.length === 0}
                      multiple={kind === "photo"}
                      accept={acceptAttr}
                      onChange={(e) => {
                        if (e.target.files?.length) handleFiles(e.target.files);
                      }}
                      className="absolute inset-0 cursor-pointer opacity-0"
                    />
                  </div>
                )}

                {files.length > 0 && (
                  <ul className="flex flex-col gap-2">
                    {files.map((file, idx) => {
                      const key = `${file.name}-${file.size}`;
                      const st = uploads[key];
                      return (
                        <li
                          key={key}
                          className="flex items-center justify-between gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-white/75 px-3.5 py-2.5 text-sm"
                        >
                          <div className="min-w-0">
                            <p className="truncate font-medium">{file.name}</p>
                            <p className="text-xs text-[var(--muted-foreground)]">
                              {(file.size / 1024).toFixed(0)} KB
                              {st ? ` · ${st.stage === "failed" ? `failed: ${st.message}` : st.stage}` : ""}
                            </p>
                          </div>
                          {!submitting && (
                            <button
                              type="button"
                              aria-label="Remove file"
                              onClick={() => setFiles((curr) => curr.filter((_, i) => i !== idx))}
                              className="rounded-full p-1 hover:bg-black/5"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}

                <label className="field">
                  {needsFiles ? "Caption or story (optional)" : "Your message, story, or blessing"}
                  <textarea
                    value={body}
                    onChange={(event) => setBody(event.target.value)}
                    required={!needsFiles}
                    rows={needsFiles ? 3 : 5}
                    maxLength={20000}
                    placeholder={
                      needsFiles
                        ? "Add a note about this moment…"
                        : "Write your favorite memory, story, or blessing…"
                    }
                  />
                </label>

                <label className="field">
                  Your name
                  <input
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    disabled={anonymous}
                    maxLength={80}
                    placeholder="e.g., Aunt Sarah"
                    className="disabled:opacity-50"
                  />
                </label>

                <div className="flex flex-wrap gap-4 text-sm">
                  {space.space.allow_anonymous !== false && (
                    <label className="inline-flex cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={anonymous}
                        onChange={(e) => setAnonymous(e.target.checked)}
                        className="h-4 w-4 accent-[var(--primary)]"
                      />
                      Submit anonymously
                    </label>
                  )}
                  {kind === "message" && (
                    <label className="inline-flex cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isPrivate}
                        onChange={(e) => setIsPrivate(e.target.checked)}
                        className="h-4 w-4 accent-[var(--primary)]"
                      />
                      <Lock className="h-3.5 w-3.5 text-[var(--bronze)]" />
                      Private note to the host only
                    </label>
                  )}
                </div>

                <div className="flex items-start gap-2.5 rounded-[var(--radius)] bg-[var(--sage)]/45 px-4 py-3 text-xs text-[var(--foreground)]">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary)]" />
                  <span>
                    Your memory is uploaded securely to private storage and shared with the host.
                    Private notes never enter shared AI processing.
                  </span>
                </div>

                {error && (
                  <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
                    {error}
                  </p>
                )}

                <Button type="submit" disabled={submitting} className="w-full">
                  {submitting ? "Uploading & sending…" : "Send memory"}
                </Button>
              </form>
            </GlassCard>
          )}
        </FadeInUp>
      </main>
    </div>
  );
}
