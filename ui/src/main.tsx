import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

// No StrictMode: its double-run effects would start every timed stimulus sequence twice.
createRoot(document.getElementById("root")!).render(<App />);
