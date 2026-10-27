// Serve MediaPipe's wasm from our own origin instead of a CDN.
import { cpSync } from "node:fs";

cpSync("node_modules/@mediapipe/tasks-vision/wasm", "public/mediapipe/wasm", { recursive: true });
