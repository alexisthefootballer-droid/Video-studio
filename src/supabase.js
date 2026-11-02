import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY;

// Supabase is optional while setting up: the app still loads without it.
export const supabase = url && key ? createClient(url, key) : null;
