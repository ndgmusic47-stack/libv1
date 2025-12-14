import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Timeline from '../components/Timeline';
import MistLayer from '../components/MistLayer';
import ErrorBoundary from '../components/ErrorBoundary';
import BeatStage from '../components/stages/BeatStage';
import LyricsStage from '../components/stages/LyricsStage';
import UploadStage from '../components/stages/UploadStage';
import MixStage from '../components/stages/MixStage';
import ReleaseStage from '../components/stages/ReleaseStage';
import ContentStage from '../components/stages/ContentStage';
import StageWrapper from '../components/stages/StageWrapper';
import AnalyticsDashboard from '../components/AnalyticsDashboard';
import ManageProjectsModal from '../components/ManageProjectsModal';
import UpgradeModal from '../components/UpgradeModal';
import { api } from '../utils/api';
import '../styles/ErrorBoundary.css';

export default function AppPage() {
  const [activeStage, setActiveStage] = useState(null);
  const [isStageOpen, setIsStageOpen] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [showManageProjects, setShowManageProjects] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [upgradeFeature, setUpgradeFeature] = useState(null);
  const [currentProjectId, setCurrentProjectId] = useState(null);
  const [saveToast, setSaveToast] = useState(null);
  const [currentStage, setCurrentStage] = useState('beat');
  const [completedStages, setCompletedStages] = useState({});
  const timelineRef = useRef(null);
  // sessionId is now initialized in main.jsx and stored in localStorage with key 'session_id'
  const sessionId = localStorage.getItem('session_id') || '';
  const hasShownExpiredModal = useRef(false);
  const [sessionData, setSessionData] = useState({
    beatFile: null,
    lyricsData: null,
    vocalFile: null,
    masterFile: null,
    genre: 'hip hop',
    mood: 'energetic',
    trackTitle: 'My Track',
  });

  // NP22: Global stage order for full workflow
  const stageOrder = [
    "beat",      // Beat creation module  
    "lyrics",    // Lyrics module
    "upload",    // Beat upload module
    "mix",       // Mix Stage
    "release",   // Release Pack module
    "content",   // Content/Viral module
    "analytics"  // Analytics / dashboard module
  ];

  // Load project data on mount (workflow status is tracked in project memory)
  useEffect(() => {
    loadProjectData();
  }, [sessionId]);

  const loadProjectData = async () => {
    try {
      const project = await api.getProject(sessionId);
      if (project && project.workflow) {
        setCurrentStage(project.workflow.current_stage || 'beat');
        // Convert array to object format for tick system
        const completedArray = project.workflow.completed_stages || [];
        const completedObj = {};
        completedArray.forEach(stage => {
          completedObj[stage] = true;
        });
        setCompletedStages(completedObj);
      }
    } catch (err) {
      // New session - use defaults
    }
  };

  const completeCurrentStage = async (stage) => {
    // Phase 1: Mark stage as complete using object format for tick system
    setCompletedStages(prev => ({ ...prev, [stage]: true }));
    
    // Sync with backend to get updated project state after stage completion
    try {
      await api.syncProject(sessionId, updateSessionData);
    } catch (err) {
      console.error('Failed to sync project after stage completion:', err);
    }
    
    // Suggest next stage using NP22 stage order
    const currentIndex = stageOrder.indexOf(stage);
    if (currentIndex < stageOrder.length - 1) {
      const nextStage = stageOrder[currentIndex + 1];
      setCurrentStage(nextStage);
    }
  };

  const updateSessionData = (data) => {
    setSessionData((prev) => ({ ...prev, ...data }));
  };

  const handleStageClick = (stageId) => {
    setActiveStage(stageId);
    setIsStageOpen(true);
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleClose = () => {
    setActiveStage(null);
    setIsStageOpen(false);
  };

  const handleBackToTimeline = () => {
    setActiveStage(null);
    setIsStageOpen(false);
  };

  const openStage = (stageId) => {
    setActiveStage(stageId);
    setIsStageOpen(true);
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const goToNextStage = () => {
    // Prefer activeStage, but fall back to currentStage if needed
    const current = activeStage || currentStage;

    const index = stageOrder.indexOf(current);
    if (index === -1) {
      console.warn(
        '[Navigation] goToNextStage: current stage not found in stageOrder',
        { activeStage, currentStage, stageOrder }
      );
      return;
    }

    if (index >= stageOrder.length - 1) {
      console.info('[Navigation] goToNextStage: already at last stage', {
        current,
        index,
      });
      return;
    }

    const nextStage = stageOrder[index + 1];
    openStage(nextStage);
  };

  const goToPreviousStage = () => {
    // Prefer activeStage, but fall back to currentStage if needed
    const current = activeStage || currentStage;

    const index = stageOrder.indexOf(current);
    if (index === -1) {
      console.warn(
        '[Navigation] goToPreviousStage: current stage not found in stageOrder',
        { activeStage, currentStage, stageOrder }
      );
      return;
    }

    if (index <= 0) {
      console.info('[Navigation] goToPreviousStage: already at first stage', {
        current,
        index,
      });
      return;
    }

    const prevStage = stageOrder[index - 1];
    openStage(prevStage);
  };

  const handleAnalyticsClose = () => {
    setShowAnalytics(false);
  };

  const handleAnalyticsClick = () => {
    setShowAnalytics(true);
  };

  const openUpgradeModal = (feature) => {
    setUpgradeFeature(feature);
    setShowUpgradeModal(true);
  };

  const handleUpgradeToPro = async () => {
    try {
      const result = await api.createCheckoutSession();
      if (result && result.url) {
        window.location.href = result.url;
      } else {
        console.error('No checkout URL returned');
      }
    } catch (err) {
      console.error('Failed to create checkout session:', err);
      // Show error or fallback to modal
      openUpgradeModal(null);
    }
  };

  const handleSaveProject = async () => {
    try {
      // Get current project data
      const project = await api.getProject(sessionId);
      if (!project) {
        throw new Error('No project data to save');
      }

      // Save project
      const result = await api.saveProject(null, currentProjectId, project);
      
      setCurrentProjectId(result.projectId);
      
      // Show success toast
      setSaveToast('Project saved!');
      setTimeout(() => setSaveToast(null), 3000);
    } catch (err) {
      console.error('Failed to save project:', err);
      setSaveToast('Failed to save project');
      setTimeout(() => setSaveToast(null), 3000);
    }
  };

  const handleLoadProject = async (projectData) => {
    try {
      // Import project data into current session
      // The backend will handle importing the data when we save it to the current session
      // For now, update UI state from loaded project
      if (projectData.projectData) {
        const data = projectData.projectData;
        
        // Update workflow state
        if (data.workflow) {
          setCurrentStage(data.workflow.current_stage || 'beat');
          const completedArray = data.workflow.completed_stages || [];
          const completedObj = {};
          completedArray.forEach(stage => {
            completedObj[stage] = true;
          });
          setCompletedStages(completedObj);
        }
        
        // Update session data
        if (data.metadata) {
          updateSessionData({
            genre: data.metadata.genre || 'hip hop',
            mood: data.metadata.mood || 'energetic',
            trackTitle: data.metadata.track_title || 'My Track',
          });
        }
        
        // Set project ID so future saves update this project
        setCurrentProjectId(projectData.projectId);
        
        // Save the loaded data to current session (this imports it into projectMemory)
        // The backend will merge this with the current session
        await api.saveProject(projectData.projectId, data);
      }
      
      // Close any open stages and return to timeline
      setActiveStage(null);
      setIsStageOpen(false);
      
      // Reload project data to sync with backend
      await loadProjectData();
    } catch (err) {
      console.error('Failed to load project:', err);
    }
  };


  const renderStage = () => {
    const currentForNav = activeStage || currentStage;
    const currentIndex = stageOrder.indexOf(currentForNav);

    const isFirstStage = currentIndex <= 0;
    const isLastStage = currentIndex === stageOrder.length - 1 && currentIndex >= 0;

    const commonProps = {
      openUpgradeModal,
      sessionId,
      sessionData,
      updateSessionData,
      onClose: handleClose,
      // Hide Next on the last stage
      onNext: isLastStage ? undefined : goToNextStage,
      // Hide Back on the first stage
      onBack: isFirstStage ? undefined : goToPreviousStage,
      completeStage: completeCurrentStage,
    };

    switch (activeStage) {
      case 'beat':
        return <BeatStage {...commonProps} />;
      case 'lyrics':
        return <LyricsStage {...commonProps} />;
      case 'upload':
        return <UploadStage {...commonProps} />;
      case 'mix':
        return <MixStage {...commonProps} />;
      case 'release':
        return (
          <ReleaseStage
            {...commonProps}
            masterFile={sessionData?.masterFile}
            onComplete={(stageKey, url) => {
              completeCurrentStage(stageKey);
              updateSessionData({ masterFile: url });
            }}
          />
        );
      case 'content':
        return <ContentStage {...commonProps} />;
      case 'analytics':
        return (
          <StageWrapper
            title="Analytics"
            icon="📊"
            onBack={goToPreviousStage}
            onClose={handleClose}
          >
            <AnalyticsDashboard
              sessionId={sessionId}
              projectId={currentProjectId}
              sessionData={sessionData}
            />
          </StageWrapper>
        );
      default:
        return null;
    }
  };

  return (
    <div className="app-root">
      <MistLayer activeStage={activeStage || currentStage} />

      {!showAnalytics && !isStageOpen && (
        <div className="timeline-centered">
          <Timeline
            ref={timelineRef}
            currentStage={currentStage}
            activeStage={activeStage}
            completedStages={completedStages}
            onStageClick={handleStageClick}
            showBackButton={!!activeStage}
            onBackToTimeline={handleBackToTimeline}
            openUpgradeModal={openUpgradeModal}
          />
        </div>
      )}

      <main className={`stage-screen ${isStageOpen ? 'fullscreen' : ''} ${!activeStage ? 'no-stage-active' : ''}`}>
        <ErrorBoundary onReset={() => setActiveStage(null)}>
          {renderStage()}
        </ErrorBoundary>
      </main>

      {/* Analytics Dashboard */}
      <AnimatePresence>
        {showAnalytics && (
          <ErrorBoundary onReset={() => setShowAnalytics(false)}>
            <AnalyticsDashboard
              sessionId={sessionId}
              onClose={handleAnalyticsClose}
            />
          </ErrorBoundary>
        )}
      </AnimatePresence>

      {/* Manage Projects Modal */}
      <ManageProjectsModal 
        isOpen={showManageProjects} 
        onClose={() => setShowManageProjects(false)}
        onLoadProject={handleLoadProject}
      />

      {/* Upgrade Modal */}
      <UpgradeModal 
        isOpen={showUpgradeModal} 
        onClose={() => {
          setShowUpgradeModal(false);
          setUpgradeFeature(null);
        }}
        feature={upgradeFeature}
      />

      {/* Save Toast */}
      {saveToast && (
        <motion.div
          className="fixed bottom-4 right-4 bg-green-600 text-white px-6 py-3 rounded-lg shadow-lg z-50 font-poppins"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
        >
          {saveToast}
        </motion.div>
      )}

    </div>
  );
}

