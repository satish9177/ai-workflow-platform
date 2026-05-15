import type { ReactNode } from "react";

type SplitPaneProps = {
  left: ReactNode;
  right: ReactNode;
};

export default function SplitPane({ left, right }: SplitPaneProps) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
      <div className="min-w-0">{left}</div>
      <div className="min-w-0">{right}</div>
    </div>
  );
}
