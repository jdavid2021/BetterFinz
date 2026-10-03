import type {Metadata} from "next";
import "./globals.css";
import "./insights.css";
import {Providers} from "@/components/providers";
import Link from "next/link";
export const metadata:Metadata={title:"FinLeash — Know what will clear",description:"Personal payment coverage planning",manifest:"/site.webmanifest",icons:{icon:[{url:"/favicon.ico?v=20260810-2"},{url:"/favicon-16x16.png?v=20260810-2",sizes:"16x16",type:"image/png"},{url:"/favicon-32x32.png?v=20260810-2",sizes:"32x32",type:"image/png"},{url:"/favicon-48x48.png?v=20260810-2",sizes:"48x48",type:"image/png"},{url:"/favicon-96x96.png?v=20260810-2",sizes:"96x96",type:"image/png"}],apple:[{url:"/apple-touch-icon.png?v=20260810-2",sizes:"180x180",type:"image/png"}]}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><Providers>{children}</Providers><footer className="legal-footer"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer></body></html>}
