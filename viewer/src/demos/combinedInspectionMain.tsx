import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CombinedInspectionDemo } from "./CombinedInspectionDemo";
import "../index.css";

createRoot(document.getElementById("root")!).render(<StrictMode><CombinedInspectionDemo /></StrictMode>);
