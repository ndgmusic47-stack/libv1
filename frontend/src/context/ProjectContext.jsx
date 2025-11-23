import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';

const ProjectContext = createContext(null);

export function ProjectProvider({ children, sessionId }) {
  const [projectData, setProjectData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load project data on mount and when sessionId changes
  useEffect(() => {
    if (!sessionId) {
      setLoading(false);
      return;
    }

    const loadProject = async () => {
      try {
        const project = await api.getProject(sessionId);
        if (project) {
          // Ensure mix has canonical structure
          const normalizedProject = normalizeProjectData(project);
          setProjectData(normalizedProject);
        }
      } catch (err) {
        console.error('Failed to load project:', err);
        setProjectData(null);
      } finally {
        setLoading(false);
      }
    };

    loadProject();
  }, [sessionId]);

  // Normalize project data to ensure canonical mix structure
  const normalizeProjectData = (project) => {
    if (!project) return project;

    // Ensure mix has canonical structure: { mix_url, final_output, completed }
    if (project.mix) {
      const mix = project.mix;
      const mixUrl = mix.mix_url || mix.url || mix.path || null;
      const finalOutput = mix.final_output || mixUrl || null;
      const completed = mix.completed === true;

      project.mix = {
        mix_url: mixUrl,
        final_output: finalOutput,
        completed: completed
      };
    } else {
      // Initialize empty mix structure if it doesn't exist
      project.mix = {
        mix_url: null,
        final_output: null,
        completed: false
      };
    }

    return project;
  };

  // Update project data (ensures canonical mix structure)
  const updateProject = useCallback((updates) => {
    setProjectData((prev) => {
      const updated = { ...prev, ...updates };

      // Ensure mix structure is canonical
      if (updated.mix) {
        const mix = updated.mix;
        const mixUrl = mix.mix_url || mix.url || mix.path || prev?.mix?.mix_url || null;
        const finalOutput = mix.final_output || mixUrl || prev?.mix?.final_output || null;
        const completed = mix.completed === true || prev?.mix?.completed === true;

        updated.mix = {
          mix_url: mixUrl,
          final_output: finalOutput,
          completed: completed
        };
      } else if (prev?.mix) {
        // Preserve existing mix structure if not updating
        updated.mix = prev.mix;
      } else {
        // Initialize empty mix structure
        updated.mix = {
          mix_url: null,
          final_output: null,
          completed: false
        };
      }

      return updated;
    });
  }, []);

  // Sync project with backend
  const syncProject = useCallback(async () => {
    if (!sessionId) return;

    try {
      const project = await api.getProject(sessionId);
      if (project) {
        const normalizedProject = normalizeProjectData(project);
        setProjectData(normalizedProject);
      }
    } catch (err) {
      console.error('Failed to sync project:', err);
    }
  }, [sessionId]);

  const value = {
    projectData,
    updateProject,
    syncProject,
    loading
  };

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useProject must be used within ProjectProvider');
  }
  return context;
}

