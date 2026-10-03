"use client";
import * as Sentry from "@sentry/nextjs";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {useState} from "react";
export function Providers({children}:{children:React.ReactNode}){const [client]=useState(()=>new QueryClient({defaultOptions:{queries:{staleTime:30_000,retry:1}}}));return <Sentry.ErrorBoundary fallback={<main><h1>Something went wrong</h1><p role="alert">Please reload the page and try again.</p></main>}><QueryClientProvider client={client}>{children}</QueryClientProvider></Sentry.ErrorBoundary>}
