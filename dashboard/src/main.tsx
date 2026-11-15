import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import { applyThemeChoice, readThemeChoice } from "./theme";

// Apply the saved theme before the first render, so the page does not change
// colour after it appears.
applyThemeChoice(readThemeChoice());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
