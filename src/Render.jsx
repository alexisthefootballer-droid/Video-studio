import React from "react";

export default function Render() {
  return (
    <div className="card">
      <p>The website designs the video. The final video is made by the free Colab render step, because video needs a powerful GPU that free website hosting does not have.</p>
      <ol>
        <li>Save your scenes in tab 2.</li>
        <li>Open the Colab notebook and run the render cell (we will add it next).</li>
        <li>Download the finished video from Colab.</li>
      </ol>
      <p className="muted">Nothing here costs money.</p>
    </div>
  );
}
