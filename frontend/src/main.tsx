import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import "@xyflow/react/dist/style.css";
import App from "./App";
import { EmbedView } from "./components/EmbedView";
import { isEmbedRoute } from "./lib/modeRoute";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("root element missing");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    {isEmbedRoute() ? <EmbedView /> : <App />}
  </React.StrictMode>,
);
