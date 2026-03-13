import React from "react";
import { createRoot } from "react-dom/client";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import App from "./components/App";

/* global Office */

const rootElement = document.getElementById("root")!;
const root = createRoot(rootElement);

const render = () => {
  root.render(
    <FluentProvider theme={webLightTheme}>
      <App />
    </FluentProvider>
  );
};

// Initialize Office.js, then render React.
// In standalone browser mode (no Excel), render immediately.
if (typeof Office !== "undefined" && Office.onReady) {
  Office.onReady(() => render());
} else {
  render();
}
