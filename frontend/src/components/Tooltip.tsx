'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Info, HelpCircle } from 'lucide-react';

interface TooltipProps {
  content: React.ReactNode;
  children?: React.ReactNode;
  title?: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
  variant?: 'icon' | 'badge' | 'wrapper';
  className?: string;
  maxWidth?: string;
}

export function Tooltip({
  content,
  children,
  title,
  position = 'top',
  variant = 'icon',
  className = '',
  maxWidth = 'max-w-xs',
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const showTooltip = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setIsVisible(true);
  };

  const hideTooltip = () => {
    timeoutRef.current = setTimeout(() => {
      setIsVisible(false);
    }, 100);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <div
      className={`relative inline-flex items-center ${className}`}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {variant === 'icon' ? (
        <button
          type="button"
          aria-label="Info"
          className="text-slate-400 hover:text-amber-400 p-0.5 rounded-full hover:bg-slate-800/80 transition-colors focus:outline-none focus:ring-1 focus:ring-amber-400"
        >
          <HelpCircle className="w-3.5 h-3.5" />
        </button>
      ) : variant === 'badge' ? (
        <button
          type="button"
          className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/80 hover:bg-amber-500/20 text-slate-400 hover:text-amber-300 border border-slate-700/60 transition-colors flex items-center gap-1"
        >
          <Info className="w-2.5 h-2.5 text-amber-400" />
          <span>Explain</span>
        </button>
      ) : (
        children
      )}

      {isVisible && (
        <div
          role="tooltip"
          className={`absolute z-50 ${positionClasses[position]} ${maxWidth} pointer-events-none transition-all duration-200 animate-in fade-in zoom-in-95`}
        >
          <div className="bg-slate-900/95 backdrop-blur-md border border-amber-500/30 text-slate-200 text-xs rounded-xl p-3 shadow-2xl shadow-black/80 font-sans leading-relaxed">
            {title && (
              <div className="font-semibold text-amber-300 flex items-center gap-1.5 pb-1.5 mb-1.5 border-b border-slate-800">
                <Info className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span>{title}</span>
              </div>
            )}
            <div className="text-slate-300 text-[11px] font-normal leading-normal">{content}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tooltip;
