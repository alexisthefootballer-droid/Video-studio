import React, { useState } from "react";
import { supabase } from "./supabase.js";

const EXAMPLE = `[
  { "start": 0, "layout": "title", "kicker": "Private matchmaking", "title": "15 Rules for Successful Matchmaking", "subtitle": "AlexisTheFootballer" },
  { "start": 4.5, "layout": "split", "kicker": "Rule 01", "title": "Be honest from the beginning.", "subtitle": "Foundation of connection" },
  { "start": 11, "layout": "image", "kicker": "Real talk", "title": "Real conversations build real love", "image": "photo1.jpg" }
]`;

export default function Scenes() {
  const [text, setText] = useState(EXAMPLE);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  function check() {
    try { JSON.parse(text); setErr(""); setMsg("Looks good."); }
    catch (e) { setErr("Not valid yet: " + e.message); setMsg(""); }
  }

  async function save() {
    check();
    if (err) return;
    if (!supabase) return setMsg("Add your Supabase keys first (see README).");
    const scenes = JSON.parse(text);
    const { error } = await supabase.from("scenes").insert({ title: scenes[0]?.title || "Untitled", scenes });
    setMsg(error ? "Error: " + error.message : "Saved to your project.");
  }

  return (
    <div className="card">
      <p className="muted">Each scene has a start time in seconds, a layout (title, split, image, presenter), and text. The rules list can be any length.</p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} />
      <p className="err">{err}</p>
      <p className="muted">{msg}</p>
      <button className="btn" onClick={check}>Check</button>{" "}
      <button className="btn" onClick={save}>Save scenes</button>
    </div>
  );
}
