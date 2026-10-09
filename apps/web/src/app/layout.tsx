import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'AI Film Studio', description: '从故事到成片的创作者工作室' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
