import Link from "next/link";
import { YouTubeConnectionSettings } from "../../components/YouTubeConnectionSettings";

export default function SettingsPage() {
  return <main className="mx-auto max-w-4xl space-y-6 p-6">
    <header className="flex items-center justify-between"><h1 className="text-2xl font-bold">設定</h1>
      <Link href="/upload" className="underline">動画作成へ戻る</Link></header>
    <YouTubeConnectionSettings />
  </main>;
}
