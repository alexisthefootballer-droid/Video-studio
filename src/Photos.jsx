import React, { useEffect, useState } from "react";
import { supabase } from "./supabase.js";

export default function Photos() {
  const [files, setFiles] = useState([]);
  const [msg, setMsg] = useState("");

  async function load() {
    if (!supabase) return;
    const { data } = await supabase.storage.from("photos").list("", { limit: 200 });
    setFiles((data || []).filter((f) => f.name));
  }
  useEffect(() => { load(); }, []);

  async function upload(e) {
    if (!supabase) return setMsg("Add your Supabase keys first (see README).");
    setMsg("Uploading...");
    for (const f of e.target.files) {
      const name = `${Date.now()}-${f.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
      const { error } = await supabase.storage.from("photos").upload(name, f);
      if (error) return setMsg("Error: " + error.message);
    }
    setMsg("Done. Photos saved.");
    load();
  }

  const url = (name) => supabase.storage.from("photos").getPublicUrl(name).data.publicUrl;

  return (
    <>
      <div className="card">
        <p>Choose photos for the backgrounds. Use only photos you have permission to use.</p>
        <input type="file" accept="image/*" multiple onChange={upload} />
        <p className="muted">{msg}</p>
      </div>
      <div className="grid">
        {files.map((f) => <img key={f.name} src={url(f.name)} alt={f.name} />)}
      </div>
    </>
  );
}
