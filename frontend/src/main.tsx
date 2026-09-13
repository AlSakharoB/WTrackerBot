import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./app/App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/shell.css";
import "./styles/components.css";
import "./styles.css";
import "./styles/pages/ration.css";
import { createTelegramAdapter } from "./telegram/adapter";

const telegram = createTelegramAdapter();
telegram.initialize();

const queryClient = new QueryClient();
const root = document.getElementById("root");
if (!root) throw new Error("Root element was not found");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App telegram={telegram} />
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
);
