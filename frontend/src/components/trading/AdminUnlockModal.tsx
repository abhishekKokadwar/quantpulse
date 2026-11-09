'use client';

import React, { useState } from 'react';
import { Lock, Unlock, X, AlertTriangle, Key } from 'lucide-react';

interface AdminUnlockModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUnlock: (token: string) => boolean;
}

export const AdminUnlockModal: React.FC<AdminUnlockModalProps> = ({
  isOpen,
  onClose,
  onUnlock,
}) => {
  const [tokenInput, setTokenInput] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const success = onUnlock(tokenInput.trim());
    if (success) {
      setTokenInput('');
      onClose();
    } else {
      setErrorMessage('Invalid administrative security token. Access denied.');
    }
  };

  const handleUseDefault = () => {
    setTokenInput('QUANT_PULSE_SECURE_TOKEN_2026');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="w-full max-w-md bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl shadow-2xl p-6 flex flex-col gap-5 animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1A1A1A] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#141414] border border-[#262626]">
              <Lock className="w-4 h-4 text-[#FFFFFF]" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#FFFFFF] uppercase tracking-wide">Disarm Emergency Kill Switch</h3>
              <p className="text-xs text-[#A3A3A3]">Administrative authorization required</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[#A3A3A3] hover:text-[#FFFFFF] hover:bg-[#171717] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Warning Banner */}
        <div className="bg-[#121212] border border-rose-900/40 p-3 rounded-lg flex items-start gap-2.5 text-xs text-[#A3A3A3]">
          <AlertTriangle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
          <span>
            The system is currently in <strong className="text-[#FFFFFF]">EMERGENCY_HALT</strong> mode. Disarming the circuit breaker will re-enable live algorithmic order execution.
          </span>
        </div>

        {/* Unlock Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-[#FFFFFF] flex items-center justify-between">
              <span>Security Token</span>
              <button
                type="button"
                onClick={handleUseDefault}
                className="text-[10px] text-[#A3A3A3] hover:text-[#FFFFFF] underline"
              >
                Autofill Demo Key
              </button>
            </label>
            <div className="relative">
              <Key className="w-4 h-4 text-[#525252] absolute left-3 top-3" />
              <input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Enter master admin credential..."
                className="w-full bg-[#000000] border border-[#1A1A1A] rounded-lg pl-9 pr-3 py-2 text-sm text-[#FFFFFF] font-mono focus:outline-none focus:border-[#404040] transition-colors"
                autoFocus
              />
            </div>
            {errorMessage && (
              <span className="text-[11px] text-rose-400 font-medium">{errorMessage}</span>
            )}
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] border border-[#1A1A1A] rounded-lg text-xs font-medium transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-[#FFFFFF] hover:bg-[#E5E5E5] text-[#000000] rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm"
            >
              <Unlock className="w-3.5 h-3.5" />
              <span>Authorize & Disarm</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
