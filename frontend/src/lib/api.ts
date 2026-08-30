// ── API Client & Type Definitions for Agentic Screenwriting Studio ────────────

export interface Beat {
  beat_number?: number;
  id?: number;
  title?: string;
  type?: string;
  description?: string;
  act?: string;
  target_page?: number;
  scene_ideas?: string[];
  [key: string]: any;
}

export interface Scene {
  scene_number: number;
  slugline: string;
  location?: string;
  time_of_day?: string;
  summary?: string;
  dialogue?: any[];
  mood_board_image?: string;
  mood_description?: string;
  table_read_audio?: string;
  soundtrack_audio?: string;
  concept_video?: string;
  script_text?: string;
  status?: string;
  characters?: string[];
  [key: string]: any;
}

export interface MediaAnalysis {
  media_id: string;
  project_id?: string;
  filename?: string;
  media_type?: 'image' | 'video' | 'audio';
  media_url: string;
  caption?: string;
  structured_description?: any;
  scene_number?: number | null;
  is_canon?: boolean;
  created_at?: string;
  [key: string]: any;
}

export interface ScriptState {
  title?: string;
  logline?: string;
  genre?: string;
  theme?: string;
  target_audience?: string;
  format?: string;
  beat_sheet?: Beat[];
  scenes?: Scene[];
  characters?: Record<string, any>;
  media_analyses?: MediaAnalysis[];
  [key: string]: any;
}

export interface ChatResponse {
  response_text: string;
  project_id?: string;
  agent?: string;
  state?: ScriptState;
}

export interface AgentStatus {
  name: string;
  display_name: string;
  status: 'idle' | 'working' | 'active' | 'error';
  description?: string;
  last_active?: string | null;
  icon?: string;
  current_task?: string;
}

export interface ClickHouseHealth {
  status: string;
  connected: boolean;
  database?: string;
  tables?: string[];
  latency_ms?: number;
  [key: string]: any;
}

export interface ProjectListItem {
  project_id: string;
  title: string;
  logline?: string;
  created_at: string;
  updated_at: string;
  scene_count?: number;
  character_count?: number;
  [key: string]: any;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function getWebSocketUrl(): string {
  const wsProtocol = API_BASE.startsWith('https') ? 'wss' : 'ws';
  const host = API_BASE.replace(/^https?:\/\//, '');
  return `${wsProtocol}://${host}/ws/events`;
}

export function persistProjectId(projectId: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('studio_active_project_id', projectId);
  }
}

export function loadPersistedProjectId(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('studio_active_project_id');
  }
  return null;
}

export async function sendMessage(params: {
  message: string;
  project_id?: string;
}): Promise<ChatResponse> {
  try {
    // Long timeout for agent processing (agents + TTS + video gen can take minutes)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300_000); // 5 minutes
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: controller.signal,
      });
      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }
      return await res.json();
    } finally {
      clearTimeout(timeoutId);
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw new Error('Request timed out after 5 minutes. The backend may still be processing — check back in a moment.');
    }
    throw new Error(err?.message || 'Failed to connect to backend API server.');
  }
}

export async function getScriptState(projectId: string): Promise<ScriptState> {
  try {
    const res = await fetch(`${API_BASE}/api/script/${projectId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch script state for project ${projectId}`);
    }
    return await res.json();
  } catch (err: any) {
    console.warn(`[API] getScriptState error:`, err);
    throw err;
  }
}

export async function getAgentStatuses(): Promise<AgentStatus[]> {
  try {
    const res = await fetch(`${API_BASE}/api/agents/status`);
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.agents)) return data.agents;
    return [];
  } catch {
    return [];
  }
}

export async function getClickHouseHealth(): Promise<ClickHouseHealth> {
  try {
    const res = await fetch(`${API_BASE}/api/health/clickhouse`);
    if (!res.ok) {
      return { status: 'disconnected', connected: false };
    }
    return await res.json();
  } catch {
    return { status: 'offline', connected: false };
  }
}

export async function recoverSession(projectId: string): Promise<any> {
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${projectId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function getChatHistory(projectId: string): Promise<{ messages: any[] }> {
  try {
    const res = await fetch(`${API_BASE}/api/chat/history/${projectId}`);
    if (!res.ok) return { messages: [] };
    return await res.json();
  } catch {
    return { messages: [] };
  }
}

export async function listProjects(): Promise<ProjectListItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/projects`);
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.projects)) return data.projects;
    return [];
  } catch {
    return [];
  }
}

export async function deleteProject(projectId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}`, {
      method: 'DELETE',
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function uploadMedia(
  file: File,
  projectId: string,
  sceneNum: number | null,
  isCanon: boolean
): Promise<MediaAnalysis> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('project_id', projectId);
    if (sceneNum !== null) {
      formData.append('scene_number', sceneNum.toString());
    }
    formData.append('is_canon', isCanon.toString());

    // Long timeout for video/image analysis (Gemini multimodal can be slow)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180_000); // 3 minutes
    try {
      const res = await fetch(`${API_BASE}/api/media/upload`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || `Upload failed with status ${res.status}`);
      }
      return await res.json();
    } finally {
      clearTimeout(timeoutId);
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw new Error('Media upload timed out. The analysis may still be processing.');
    }
    throw new Error(err?.message || 'Media upload failed.');
  }
}

export async function getProjectMedia(projectId: string): Promise<MediaAnalysis[]> {
  try {
    const res = await fetch(`${API_BASE}/api/media/project/${projectId}`);
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.media)) return data.media;
    return [];
  } catch {
    return [];
  }
}

export async function updateMediaItem(
  projectId: string,
  mediaId: string,
  updates: Partial<MediaAnalysis>
): Promise<any> {
  try {
    const res = await fetch(`${API_BASE}/api/media/project/${projectId}/${mediaId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) {
      throw new Error(`Failed to update media item ${mediaId}`);
    }
    return await res.json();
  } catch (err: any) {
    throw new Error(err?.message || `Failed to update media item.`);
  }
}

export async function deleteMediaItem(
  projectId: string,
  mediaId: string
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/media/project/${projectId}/${mediaId}`, {
      method: 'DELETE',
    });
    return res.ok;
  } catch {
    return false;
  }
}
