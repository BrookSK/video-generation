import { ApiError } from "./api";

export type AspectRatio = "9:16" | "16:9";
export type VideoInput = { script_text: string; avatar_id: string; scene_id: string; aspect_ratio: AspectRatio };
export type GenerationConfig = { max_script_chars: number | null; max_audio_seconds: number | null; chars_per_second: number | null };
export type JobStatus = "queued" | "processing" | "ready" | "failed";
export type JobCreated = { id: string; status: JobStatus; status_url: string };
export type VideoJob = JobCreated & VideoInput & {
  stage: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  avatar_name: string;
  scene_name: string;
  voice: string;
  origin: string;
  requested_by: string;
  download_url: string | null;
  error: { code: string; message: string } | null;
  file_exists: boolean;
  size_bytes: number | null;
  duration_seconds: number | null;
};
export type WorkerPresence = { last_heartbeat_at: string | null };

export const STATUS_LABEL: Record<JobStatus, string> = { queued: "Na fila", processing: "Processando", ready: "Pronto", failed: "Falha" };
export const STAGES = [
  { id: "compose", label: "Compor" },
  { id: "tts", label: "Voz" },
  { id: "render", label: "Animar" },
  { id: "finalize", label: "Finalizar" },
  { id: "upload", label: "Salvar" },
];
export function failure(error: unknown): string {
  return error instanceof ApiError ? error.message : "Não foi possível falar com o servidor. Tente de novo em instantes.";
}
