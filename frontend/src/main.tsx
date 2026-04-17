import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import "@xyflow/react/dist/style.css";
import App from "./App";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("root element missing");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
