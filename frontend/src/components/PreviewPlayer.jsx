import { useProject } from "../context/ProjectContext";

export default function PreviewPlayer() {
  const { projectData } = useProject();
  
  // Use ONLY the global mix URL from project context
  const audioSrc = projectData?.mix?.final_output;

  // Render audio ONLY if audioSrc exists
  if (!audioSrc) {
    return null;
  }

  return (
    <div className="w-full space-y-2">
      <label className="block text-sm text-studio-white/60 font-montserrat">
        Processed Audio
      </label>
      <div className="w-full flex justify-center">
        <audio
          controls
          src={audioSrc}
          className="w-full"
        />
      </div>
    </div>
  );
}

