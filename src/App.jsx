import React, { useState } from "react";
import { supabase } from "./supabase.js";
import Photos from "./Photos.jsx";
import Scenes from "./Scenes.jsx";
import Render from "./Render.jsx";

const TABS = [
  ["photos", "1. Upload photos"],
  ["scenes", "2. Scenes"],
  ["render", "3. Make video"],
];

export default function App() {
  const [tab, setTab] = useState("photos");
  return (
    <>
      <header>
        <h1>Video <span>Studio</span></h1>
        <span className="muted">{supabase ? "Connected" : "Not connected yet"}</span>
      </header>
      <nav>
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "" : "off"} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>
      <main>
        {tab === "photos" && <Photos />}
        {tab === "scenes" && <Scenes />}
        {tab === "render" && <Render />}
      </main>
    </>
  );
}
