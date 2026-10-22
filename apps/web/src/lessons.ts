import type { AspectRatio, JobStatus } from "./jobs";

// Tipos iguais às respostas de /panel/brand-identity e /panel/lessons.
export type BrandIdentity = {
  logo_url: string | null;
  background_color: string | null;
  accent_color: string | null;
  updated_at: string | null;
  updated_by: string | null;
};
export type Shot = "medio" | "close";
export type LessonStatus = "queued" | "assembling" | "ready" | "failed";
export type LessonError = { code: string; message: string };
export type LessonCreated = { id: string; status: LessonStatus; status_url: string; download_url: string | null };
export type LessonScene = {
  position: number;
  script_text: string;
  shot: Shot;
  job_id: string;
  status: JobStatus;
  stage: string | null;
  error: LessonError | null;
};
export type Lesson = LessonCreated & {
  avatar_id: string;
  scene_id: string;
  avatar_name: string;
  scene_name: string;
  aspect_ratio: AspectRatio;
  background_color: string;
  accent_color: string;
  requested_by: string;
  created_at: string;
  finished_at: string | null;
  error: LessonError | null;
  size_bytes: number | null;
  scenes: LessonScene[];
};
export type NewLessonInput = {
  avatar_id: string;
  scene_id: string;
  aspect_ratio: AspectRatio;
  scenes: { script_text: string; shot: Shot }[];
};

export const SHOT_LABEL: Record<Shot, string> = { medio: "Plano médio", close: "Close" };
export const LESSON_STATUS_LABEL: Record<LessonStatus, string> = {
  queued: "Gerando cenas",
  assembling: "Montando",
  ready: "Pronta",
  failed: "Falha",
};
export const MIN_SCENES = 2;
export const MAX_SCENES = 12;
export const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
