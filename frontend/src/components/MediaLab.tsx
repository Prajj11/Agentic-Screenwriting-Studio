'use client';

import { useState, useEffect, useRef } from 'react';
import {
  uploadMedia,
  getProjectMedia,
  updateMediaItem,
  deleteMediaItem,
  type MediaAnalysis,
  type Scene,
} from '@/lib/api';

interface MediaLabProps {
  projectId: string | null;
  scenes: Scene[];
  characters?: Record<string, any>;
  mediaAnalyses?: MediaAnalysis[];
  activeSceneNumber: number;
  onAction: (prompt: string) => void;
}

interface UploadProgressStep {
  step: number;
  label: string;
  status: 'pending' | 'active' | 'completed' | 'error';
}

export function MediaLab({ projectId, scenes, characters = {}, mediaAnalyses = [], activeSceneNumber, onAction }: MediaLabProps) {
  const [mediaList, setMediaList] = useState<MediaAnalysis[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'visuals' | 'portraits' | 'audio' | 'video'>('all');
  const [selectedSceneFilter, setSelectedSceneFilter] = useState<number | 'all'>('all');
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Upload state for optional external reference
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [technicalDetails, setTechnicalDetails] = useState<string | null>(null);
  const [showTechDetails, setShowTechDetails] = useState(false);

  // Scene association modal state
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [scenePromptOpen, setScenePromptOpen] = useState(false);
  const [targetSceneNumber, setTargetSceneNumber] = useState<number | null>(activeSceneNumber > 0 ? activeSceneNumber : null);
  const [isCanonUpload, setIsCanonUpload] = useState(false);

  // Multi-step progress tracking
  const [progressSteps, setProgressSteps] = useState<UploadProgressStep[]>([]);
  const [analysisType, setAnalysisType] = useState<'image' | 'video'>('image');

  const imageInputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);

  // Load media items when projectId changes
  useEffect(() => {
    if (!projectId) return;
    fetchMedia();
  }, [projectId]);

  const fetchMedia = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const data = await getProjectMedia(projectId);
      setMediaList(data);
    } catch (e) {
      console.error('Failed to fetch media list:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (file: File) => {
    if (!file) return;
    const isVideo = file.type.startsWith('video/') || /\.(mp4|mov|avi|webm|mkv)$/i.test(file.name);
    const type = isVideo ? 'video' : 'image';
    setAnalysisType(type);
    setPendingFile(file);

    if (activeSceneNumber > 0) {
      setTargetSceneNumber(activeSceneNumber);
      setScenePromptOpen(true);
    } else {
      executeUpload(file, null, false, type);
    }
  };

  const executeUpload = async (
    file: File,
    sceneNum: number | null,
    canon: boolean,
    type: 'image' | 'video'
  ) => {
    if (!projectId) return;
    setUploading(true);
    setUploadError(null);
    setTechnicalDetails(null);
    setShowTechDetails(false);

    const initialSteps: UploadProgressStep[] = type === 'video' ? [
      { step: 1, label: 'Upload received', status: 'active' },
      { step: 2, label: 'Media processed', status: 'pending' },
      { step: 3, label: 'Gemini multimodal analysis running', status: 'pending' },
      { step: 4, label: 'Extracting transcript & speaker attribution', status: 'pending' },
      { step: 5, label: 'Building visual observations timeline', status: 'pending' },
    ] : [
      { step: 1, label: 'Upload received', status: 'active' },
      { step: 2, label: 'Media processed', status: 'pending' },
      { step: 3, label: 'Gemini vision analysis running', status: 'pending' },
      { step: 4, label: 'Building structured visual breakdown', status: 'pending' },
    ];

    setProgressSteps(initialSteps);

    const progressTimer1 = setTimeout(() => {
      setProgressSteps(prev => prev.map((s, idx) => {
        if (idx === 0) return { ...s, status: 'completed' };
        if (idx === 1) return { ...s, status: 'active' };
        return s;
      }));
    }, 600);

    const progressTimer2 = setTimeout(() => {
      setProgressSteps(prev => prev.map((s, idx) => {
        if (idx === 1) return { ...s, status: 'completed' };
        if (idx === 2) return { ...s, status: 'active' };
        return s;
      }));
    }, 1800);

    const progressTimer3 = setTimeout(() => {
      setProgressSteps(prev => prev.map((s, idx) => {
        if (idx === 2) return { ...s, status: 'completed' };
        if (idx === 3) return { ...s, status: 'active' };
        return s;
      }));
    }, 4500);

    try {
      const result = await uploadMedia(file, projectId, sceneNum, canon);

      clearTimeout(progressTimer1);
      clearTimeout(progressTimer2);
      clearTimeout(progressTimer3);

      setProgressSteps(prev => prev.map(s => ({ ...s, status: 'completed' })));
      setMediaList(prev => [result, ...prev]);
      setPendingFile(null);
      setScenePromptOpen(false);
      setShowUploadModal(false);
    } catch (err: any) {
      clearTimeout(progressTimer1);
      clearTimeout(progressTimer2);
      clearTimeout(progressTimer3);

      const errMessage = err?.message || 'Media processing failed';
      setUploadError(type === 'image' ? 'Unable to analyze this image.' : 'Unable to analyze this video.');
      setTechnicalDetails(errMessage);

      setProgressSteps(prev => prev.map(s => s.status === 'active' ? { ...s, status: 'error' } : s));
    } finally {
      setUploading(false);
    }
  };

  const handleToggleCanon = async (item: MediaAnalysis) => {
    if (!projectId) return;
    const nextCanon = !item.is_canon;
    try {
      await updateMediaItem(projectId, item.media_id, { is_canon: nextCanon });
      setMediaList(prev => prev.map(m => m.media_id === item.media_id ? { ...m, is_canon: nextCanon } : m));
    } catch (e) {
      console.error('Failed to toggle canon:', e);
    }
  };

  const handleAssociateScene = async (item: MediaAnalysis, sceneNum: number | null) => {
    if (!projectId) return;
    try {
      await updateMediaItem(projectId, item.media_id, { scene_number: sceneNum });
      setMediaList(prev => prev.map(m => m.media_id === item.media_id ? { ...m, scene_number: sceneNum } : m));
    } catch (e) {
      console.error('Failed to associate scene:', e);
    }
  };

  const handleDelete = async (mediaId: string) => {
    if (!projectId) return;
    try {
      await deleteMediaItem(projectId, mediaId);
      setMediaList(prev => prev.filter(m => m.media_id !== mediaId));
    } catch (e) {
      console.error('Failed to delete media:', e);
    }
  };

  // Extract generated scene visuals from project state
  const sceneVisuals = scenes.filter(s => s.mood_board_image);
  
  // Extract character portraits from project state
  const characterPortraits = Object.values(characters).filter(c => c && (c.reference_portrait || c.visual_description));

  // Extract generated audio items (table reads & soundtracks)
  const audioTracks = scenes.flatMap(s => {
    const items = [];
    if (s.table_read_audio) {
      items.push({
        id: `tr_${s.scene_number}`,
        scene_number: s.scene_number,
        title: `Scene ${s.scene_number} Table Read`,
        type: 'Table Read (TTS)',
        url: s.table_read_audio.startsWith('http') ? s.table_read_audio : `http://localhost:8000${s.table_read_audio}`,
      });
    }
    if (s.soundtrack_audio) {
      items.push({
        id: `st_${s.scene_number}`,
        scene_number: s.scene_number,
        title: `Scene ${s.scene_number} Soundtrack Score`,
        type: 'Lyria 3 Music Score',
        url: s.soundtrack_audio.startsWith('http') ? s.soundtrack_audio : `http://localhost:8000${s.soundtrack_audio}`,
      });
    }
    return items;
  });

  // Combine fetched mediaList with scriptState mediaAnalyses
  const combinedMediaMap = new Map<string, MediaAnalysis>();
  [...mediaAnalyses, ...mediaList].forEach(item => {
    const key = item.media_id || item.filename || item.media_url;
    if (key && !combinedMediaMap.has(key)) {
      combinedMediaMap.set(key, item);
    }
  });
  const allMediaItems = Array.from(combinedMediaMap.values());

  // Filter media analyses
  const filteredMedia = allMediaItems.filter(item => {
    if (selectedSceneFilter !== 'all' && item.scene_number !== selectedSceneFilter) return false;
    return true;
  });

  const totalGeneratedCount = sceneVisuals.length + characterPortraits.length + audioTracks.length + filteredMedia.length;

  return (
    <div className="media-lab-container" style={{ padding: 'var(--space-xl) var(--space-2xl)', maxWidth: '1100px', margin: '0 auto', color: 'var(--text-primary)' }}>
      {/* ── Header ────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-md)', marginBottom: 'var(--space-xl)' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            🎬 Project Media & Production Assets
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-tertiary)', marginTop: '4px', maxWidth: '650px' }}>
            Central media library receiving all AI-generated concept art, scene mood boards, character portraits, audio scores, and video storyboards produced by your agents for this screenplay.
          </p>
        </div>

        {/* Optional External Reference Upload Trigger */}
        <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
          <button
            className="sidebar__btn"
            onClick={() => setShowUploadModal(!showUploadModal)}
            style={{ width: 'auto', background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
          >
            {showUploadModal ? '✕ Close Upload' : '+ Add External Reference (Optional)'}
          </button>
        </div>
      </div>

      {/* ── Optional Upload Box ──────────────────────────────── */}
      {showUploadModal && (
        <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '4px' }}>Upload External Reference File</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginBottom: 'var(--space-md)' }}>
            Upload custom reference images or video clips if you wish to analyze external reference material using Gemini vision.
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
            <input
              type="file"
              ref={imageInputRef}
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                if (e.target.files?.[0]) handleFileSelect(e.target.files[0]);
                e.target.value = '';
              }}
            />
            <input
              type="file"
              ref={videoInputRef}
              accept="video/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                if (e.target.files?.[0]) handleFileSelect(e.target.files[0]);
                e.target.value = '';
              }}
            />
            <button
              className="sidebar__btn"
              disabled={uploading || !projectId}
              onClick={() => imageInputRef.current?.click()}
              style={{ width: 'auto', background: 'var(--accent-primary)', color: '#fff', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
            >
              🖼 Upload Image
            </button>
            <button
              className="sidebar__btn"
              disabled={uploading || !projectId}
              onClick={() => videoInputRef.current?.click()}
              style={{ width: 'auto', background: 'var(--accent-secondary)', color: '#fff', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
            >
              🎥 Upload Video
            </button>
          </div>
        </div>
      )}

      {/* ── Scene Association Modal ────────────────── */}
      {scenePromptOpen && pendingFile && (
        <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--accent-primary)', borderRadius: 'var(--radius-md)', padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: 'var(--space-xs)' }}>
            Associate media with Scene {activeSceneNumber}?
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 'var(--space-md)' }}>
            File: <strong>{pendingFile.name}</strong>
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
            <button
              className="sidebar__btn"
              style={{ width: 'auto', background: 'var(--accent-primary)', color: '#fff', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
              onClick={() => executeUpload(pendingFile, activeSceneNumber, isCanonUpload, analysisType)}
            >
              Associate with Scene {activeSceneNumber}
            </button>
            <button
              className="sidebar__btn"
              style={{ width: 'auto', background: 'var(--surface-sunken)', padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
              onClick={() => executeUpload(pendingFile, null, isCanonUpload, analysisType)}
            >
              Keep as Project Reference
            </button>
          </div>
        </div>
      )}

      {/* ── Upload & Analysis Progress Indicator ────────────── */}
      {uploading && (
        <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-md)' }}>
            <span style={{ fontSize: '1.2rem' }}>🎥</span>
            <strong style={{ fontSize: '1rem' }}>Analyzing uploaded media...</strong>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {progressSteps.map((s) => (
              <div key={s.step} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                <span>{s.status === 'completed' ? '✓' : s.status === 'active' ? '●' : '○'}</span>
                <span style={{ color: s.status === 'active' ? 'var(--accent-primary)' : 'var(--text-tertiary)' }}>{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Category Filter Tabs ────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-md)', marginBottom: 'var(--space-lg)', background: 'var(--bg-tertiary)', padding: 'var(--space-sm) var(--space-md)', borderRadius: 'var(--radius-md)' }}>
        <div style={{ display: 'flex', gap: 'var(--space-xs)', flexWrap: 'wrap' }}>
          {[
            { key: 'all', label: `✨ All (${totalGeneratedCount})` },
            { key: 'visuals', label: `🖼 Scene Visuals (${sceneVisuals.length})` },
            { key: 'portraits', label: `👤 Character Portraits (${characterPortraits.length})` },
            { key: 'audio', label: `🎵 Audio & Scores (${audioTracks.length})` },
            { key: 'video', label: `🎥 Video Storyboards (${filteredMedia.filter(m => m.media_type === 'video').length})` },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setFilter(t.key as any)}
              style={{
                background: filter === t.key ? 'var(--bg-active)' : 'transparent',
                color: filter === t.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
                border: 'none',
                padding: '0.35rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Scene filter dropdown */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
          <span style={{ color: 'var(--text-tertiary)' }}>Filter by Scene:</span>
          <select
            value={selectedSceneFilter}
            onChange={(e) => setSelectedSceneFilter(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
            style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', padding: '0.25rem 0.5rem', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem' }}
          >
            <option value="all">All Scenes</option>
            {scenes.map(s => (
              <option key={s.scene_number} value={s.scene_number}>Scene {s.scene_number}: {s.slugline || `Scene ${s.scene_number}`}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Empty State ───────────────────────────────────────── */}
      {totalGeneratedCount === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: 'var(--space-2xl)', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-lg)', border: '1px dashed var(--border-subtle)' }}>
          <div style={{ fontSize: '3.5rem', opacity: 0.3, marginBottom: 'var(--space-md)' }}>🎬</div>
          <h3 style={{ fontSize: '1.2rem', color: 'var(--text-secondary)' }}>No Generated Media Assets Yet</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-tertiary)', marginTop: '8px', maxWidth: '500px', margin: '8px auto 0' }}>
            Ask the <strong>Visualizer Agent</strong> in the chat to <em>&ldquo;Generate visual for Scene 1&rdquo;</em>, <em>&ldquo;Create character portrait for [Name]&rdquo;</em>, or <em>&ldquo;Perform table read&rdquo;</em> to populate this media gallery!
          </p>
          <button
            className="sidebar__btn"
            style={{ width: 'auto', margin: 'var(--space-lg) auto 0', background: 'var(--accent-primary)', color: '#fff', padding: '0.5rem 1.2rem', fontSize: '0.85rem' }}
            onClick={() => onAction('Generate visuals and concept art for scene 1')}
          >
            🎨 Ask Visualizer to Generate Scene Visuals
          </button>
        </div>
      )}

      {/* ── 1. SCENE VISUALS & MOOD BOARDS ────────────────────── */}
      {(filter === 'all' || filter === 'visuals') && sceneVisuals.length > 0 && (
        <div style={{ marginBottom: 'var(--space-2xl)' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 'var(--space-md)', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            🖼️ AI-Generated Scene Visuals & Mood Boards
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 'var(--space-lg)' }}>
            {sceneVisuals.map((s) => (
              <div key={s.scene_number} style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                <img
                  src={s.mood_board_image?.startsWith('http') ? s.mood_board_image : `http://localhost:8000${s.mood_board_image}`}
                  alt={`Scene ${s.scene_number} Visual`}
                  style={{ width: '100%', height: '200px', objectFit: 'cover', display: 'block' }}
                />
                <div style={{ padding: 'var(--space-md)' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-primary)', textTransform: 'uppercase' }}>
                    SCENE {s.scene_number}
                  </div>
                  <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '2px 0 6px' }}>
                    {s.slugline || `Scene ${s.scene_number}`}
                  </h4>
                  {s.mood_description && (
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', lineHeight: 1.4 }}>
                      {s.mood_description}
                    </p>
                  )}
                  <div style={{ marginTop: 'var(--space-md)', display: 'flex', gap: 'var(--space-xs)' }}>
                    <button
                      className="sidebar__btn"
                      style={{ width: 'auto', padding: '0.3rem 0.6rem', fontSize: '0.75rem', background: 'var(--bg-secondary)' }}
                      onClick={() => onAction(`Re-generate visual concept for Scene ${s.scene_number}`)}
                    >
                      🔄 Re-generate Visual
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 2. CHARACTER PORTRAITS ────────────────────────────── */}
      {(filter === 'all' || filter === 'portraits') && characterPortraits.length > 0 && (
        <div style={{ marginBottom: 'var(--space-2xl)' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 'var(--space-md)', color: 'var(--accent-secondary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            👤 Canonical Character Visual Portraits
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 'var(--space-lg)' }}>
            {characterPortraits.map((c) => (
              <div key={c.name} style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 'var(--space-md)', display: 'flex', gap: 'var(--space-md)', alignItems: 'flex-start' }}>
                {c.reference_portrait ? (
                  <img
                    src={c.reference_portrait.startsWith('http') ? c.reference_portrait : `http://localhost:8000${c.reference_portrait}`}
                    alt={c.name}
                    style={{ width: '90px', height: '110px', objectFit: 'cover', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}
                  />
                ) : (
                  <div style={{ width: '90px', height: '110px', background: 'var(--surface-sunken)', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem', opacity: 0.4 }}>
                    👤
                  </div>
                )}
                <div style={{ flex: 1 }}>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>{c.name}</h4>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: '4px', lineHeight: 1.4 }}>
                    {c.visual_description ? (c.visual_description.length > 100 ? `${c.visual_description.slice(0, 100)}...` : c.visual_description) : (c.description || 'No portrait generated yet.')}
                  </p>
                  <button
                    className="sidebar__btn"
                    style={{ width: 'auto', marginTop: 'var(--space-sm)', padding: '0.25rem 0.5rem', fontSize: '0.75rem', background: 'var(--bg-secondary)' }}
                    onClick={() => onAction(`Generate reference portrait for character ${c.name}`)}
                  >
                    🎨 Generate Portrait
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 3. AUDIO & SCORES ─────────────────────────────────── */}
      {(filter === 'all' || filter === 'audio') && audioTracks.length > 0 && (
        <div style={{ marginBottom: 'var(--space-2xl)' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 'var(--space-md)', color: 'var(--accent-tertiary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            🎵 Generated Table Reads & Lyria 3 Scores
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 'var(--space-md)' }}>
            {audioTracks.map((t) => (
              <div key={t.id} style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 'var(--space-md)' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-tertiary)', textTransform: 'uppercase' }}>
                  {t.type}
                </div>
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '4px 0 8px' }}>{t.title}</h4>
                <audio controls src={t.url} style={{ width: '100%', height: '36px' }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 4. ANALYZED & VIDEO STORYBOARDS ───────────────────── */}
      {(filter === 'all' || filter === 'video' || filter === 'visuals') && filteredMedia.length > 0 && (
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 'var(--space-md)', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            🎥 Video Storyboards & Media References
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xl)' }}>
            {filteredMedia.map((item) => (
              <MediaCard
                key={item.media_id}
                item={item}
                scenes={scenes}
                onToggleCanon={handleToggleCanon}
                onAssociateScene={handleAssociateScene}
                onDelete={handleDelete}
                onAction={onAction}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Individual Media Card Component ──────────────────────────────────────────

interface MediaCardProps {
  item: MediaAnalysis;
  scenes: Scene[];
  onToggleCanon: (item: MediaAnalysis) => void;
  onAssociateScene: (item: MediaAnalysis, sceneNum: number | null) => void;
  onDelete: (mediaId: string) => void;
  onAction: (prompt: string) => void;
}

function MediaCard({
  item,
  scenes,
  onToggleCanon,
  onAssociateScene,
  onDelete,
  onAction,
}: MediaCardProps) {
  const isVideo = item.media_type === 'video';
  const desc = item.structured_description || {};

  const mediaFullUrl = item.media_url.startsWith('http')
    ? item.media_url
    : `http://localhost:8000${item.media_url}`;

  return (
    <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
      {/* Top Bar / Metadata */}
      <div style={{ padding: 'var(--space-md) var(--space-lg)', background: 'var(--surface-sunken)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
          <span style={{ fontSize: '0.9rem', fontWeight: 700, letterSpacing: '0.05em', color: item.is_canon ? 'var(--status-warning)' : 'var(--accent-primary)' }}>
            {item.is_canon ? (isVideo ? '⭐ CANON VIDEO' : '⭐ CANON IMAGE') : (isVideo ? '🎥 REFERENCE VIDEO' : '🖼 REFERENCE IMAGE')}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
            • {item.filename}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
          <select
            value={item.scene_number ?? 'project'}
            onChange={(e) => {
              const val = e.target.value;
              onAssociateScene(item, val === 'project' ? null : parseInt(val));
            }}
            style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}
          >
            <option value="project">Project Reference</option>
            {scenes.map(s => (
              <option key={s.scene_number} value={s.scene_number}>Scene {s.scene_number}</option>
            ))}
          </select>

          <button
            onClick={() => onToggleCanon(item)}
            style={{
              background: item.is_canon ? 'rgba(245, 166, 35, 0.2)' : 'transparent',
              color: item.is_canon ? 'var(--status-warning)' : 'var(--text-muted)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.2rem 0.5rem',
              fontSize: '0.75rem',
              cursor: 'pointer',
            }}
          >
            {item.is_canon ? '⭐ Canon' : 'Mark Canon'}
          </button>

          <button
            onClick={() => onDelete(item.media_id)}
            style={{ background: 'transparent', color: 'var(--status-error)', border: 'none', cursor: 'pointer', fontSize: '0.8rem', padding: '0 0.3rem' }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Main Content Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: isVideo ? '1fr' : '300px 1fr', gap: 'var(--space-lg)', padding: 'var(--space-lg)' }}>
        <div>
          {isVideo ? (
            <video
              controls
              src={mediaFullUrl}
              style={{ width: '100%', maxHeight: '360px', borderRadius: 'var(--radius-md)', background: '#000' }}
            />
          ) : (
            <img
              src={mediaFullUrl}
              alt={item.caption || 'Reference Image'}
              style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}
            />
          )}
        </div>

        <div>
          {isVideo ? (
            <div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: 'var(--space-md)' }}>
                {desc.video_mode === 'veo-2.0' || item.caption?.includes('Veo') ? (
                  <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px', background: 'rgba(52, 168, 83, 0.2)', color: '#34a853', fontWeight: 600, border: '1px solid rgba(52, 168, 83, 0.3)' }}>
                    🎬 Google Veo 2.0 (Vertex AI)
                  </span>
                ) : (
                  <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px', background: 'rgba(245, 166, 35, 0.2)', color: '#f5a623', fontWeight: 600, border: '1px solid rgba(245, 166, 35, 0.3)' }}>
                    ⚡ Dynamic Multi-Shot Animatic {desc.shots_count ? `(${desc.shots_count} dynamic cuts)` : ''}
                  </span>
                )}
                {desc.duration_seconds && (
                  <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px', background: 'var(--surface-sunken)', color: 'var(--text-secondary)' }}>
                    ⏱️ {desc.duration_seconds.toFixed(1)}s
                  </span>
                )}
                {desc.has_embedded_dialogue && (
                  <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px', background: 'rgba(99, 102, 241, 0.2)', color: '#818cf8' }}>
                    🎙️ Spoken Dialogue Sync
                  </span>
                )}
                {desc.has_soundtrack && (
                  <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: '4px', background: 'rgba(236, 72, 153, 0.2)', color: '#f472b6' }}>
                    🎵 Lyria 3 Soundtrack Score
                  </span>
                )}
              </div>

              {(item.caption || desc.video_summary) && (
                <div style={{ marginBottom: 'var(--space-lg)', background: 'var(--bg-primary)', padding: 'var(--space-md)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--accent-primary)', marginBottom: '4px' }}>VIDEO SUMMARY</div>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {desc.video_summary || item.caption}
                  </p>
                </div>
              )}

              {desc.transcript && desc.transcript.length > 0 && (
                <div style={{ marginBottom: 'var(--space-lg)' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--accent-secondary)', marginBottom: 'var(--space-xs)' }}>TRANSCRIPT & TIMELINE</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)', background: 'var(--bg-primary)', padding: 'var(--space-md)', borderRadius: 'var(--radius-md)', maxHeight: '200px', overflowY: 'auto' }}>
                    {desc.transcript.map((t: any, idx: number) => (
                      <div key={idx} style={{ fontSize: '0.85rem' }}>
                        {t.timestamp && (
                          <span style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', marginRight: '8px' }}>
                            {t.timestamp}
                          </span>
                        )}
                        {t.duration && (
                          <span style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', marginRight: '8px' }}>
                            [{t.duration.toFixed(1)}s]
                          </span>
                        )}
                        <strong style={{ color: 'var(--accent-primary)', marginRight: '6px' }}>{t.speaker}:</strong>
                        <span>&ldquo;{t.line || t.dialogue}&rdquo;</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--accent-primary)', marginBottom: 'var(--space-sm)' }}>AI VISUAL BREAKDOWN</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-sm)', background: 'var(--bg-primary)', padding: 'var(--space-md)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem' }}>
                {desc.setting && <div><strong style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>SETTING:</strong> <div>{desc.setting}</div></div>}
                {desc.characters && <div><strong style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>CHARACTERS:</strong> <div>{desc.characters}</div></div>}
                {desc.mood && <div><strong style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>MOOD:</strong> <div>{desc.mood}</div></div>}
                {desc.lighting && <div><strong style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>LIGHTING:</strong> <div>{desc.lighting}</div></div>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
