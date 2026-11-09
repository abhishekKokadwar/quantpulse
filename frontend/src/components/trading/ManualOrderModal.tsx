'use client';

import React, { useState } from 'react';
import { ShoppingCart, X, Check, AlertTriangle, ShieldCheck, ArrowRight } from 'lucide-react';

interface ManualOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  currentPrice: number;
  onExecuteFill: (order: { symbol: string; side: 'BUY' | 'SELL'; quantity: number; price: number }) => void;
  isKillSwitchActive: boolean;
}

export const ManualOrderModal: React.FC<ManualOrderModalProps> = ({
  isOpen,
  onClose,
  symbol,
  currentPrice,
  onExecuteFill,
  isKillSwitchActive,
}) => {
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [quantity, setQuantity] = useState('0.5');
  const [limitPrice, setLimitPrice] = useState(currentPrice.toString());
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!isOpen) return null;

  const parsedQty = parseFloat(quantity) || 0;
  const executionPrice = orderType === 'MARKET' ? currentPrice : parseFloat(limitPrice) || currentPrice;
  const totalNotional = parsedQty * executionPrice;

  // Pre-trade validation check
  const isFatFinger = totalNotional > 500_000;
  const isPriceCollarBreach = Math.abs(executionPrice - currentPrice) / currentPrice > 0.02;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isKillSwitchActive) {
      setFeedback('ORDER REJECTED: Emergency Kill Switch is engaged.');
      return;
    }
    if (isFatFinger) {
      setFeedback('ORDER REJECTED: Notional value exceeds $500,000 fat-finger limit.');
      return;
    }
    if (isPriceCollarBreach && orderType === 'LIMIT') {
      setFeedback('ORDER REJECTED: Limit price breaches 2% price collar from prevailing mid.');
      return;
    }

    onExecuteFill({
      symbol,
      side,
      quantity: parsedQty,
      price: executionPrice,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="w-full max-w-md bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl shadow-2xl p-6 flex flex-col gap-5 animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1A1A1A] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#141414] border border-[#262626]">
              <ShoppingCart className="w-4 h-4 text-[#FFFFFF]" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#FFFFFF] uppercase tracking-wide">Manual Order Simulator</h3>
              <p className="text-xs text-[#A3A3A3] font-mono">{symbol} @ ${currentPrice.toLocaleString()}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[#A3A3A3] hover:text-[#FFFFFF] hover:bg-[#171717] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Order Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Side Toggle: BUY or SELL */}
          <div className="grid grid-cols-2 gap-1.5 p-1 bg-[#000000] rounded-lg border border-[#1A1A1A]">
            <button
              type="button"
              onClick={() => setSide('BUY')}
              className={`py-2 rounded font-semibold text-xs uppercase tracking-wider transition-all border ${
                side === 'BUY'
                  ? 'bg-[#141414] border-emerald-500/50 text-emerald-400 shadow-sm'
                  : 'text-[#737373] hover:text-[#FFFFFF] border-transparent'
              }`}
            >
              BUY / LONG
            </button>
            <button
              type="button"
              onClick={() => setSide('SELL')}
              className={`py-2 rounded font-semibold text-xs uppercase tracking-wider transition-all border ${
                side === 'SELL'
                  ? 'bg-[#141414] border-rose-500/50 text-rose-400 shadow-sm'
                  : 'text-[#737373] hover:text-[#FFFFFF] border-transparent'
              }`}
            >
              SELL / SHORT
            </button>
          </div>

          {/* Type: MARKET or LIMIT */}
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-[#A3A3A3]">Execution Type</span>
            <div className="flex items-center gap-1 bg-[#000000] p-0.5 rounded border border-[#1A1A1A]">
              <button
                type="button"
                onClick={() => setOrderType('MARKET')}
                className={`px-3 py-1 rounded font-medium text-[11px] transition-all border ${
                  orderType === 'MARKET' ? 'bg-[#1A1A1A] text-[#FFFFFF] border-[#2B2B2B]' : 'text-[#737373] border-transparent hover:text-[#FFFFFF]'
                }`}
              >
                Market
              </button>
              <button
                type="button"
                onClick={() => setOrderType('LIMIT')}
                className={`px-3 py-1 rounded font-medium text-[11px] transition-all border ${
                  orderType === 'LIMIT' ? 'bg-[#1A1A1A] text-[#FFFFFF] border-[#2B2B2B]' : 'text-[#737373] border-transparent hover:text-[#FFFFFF]'
                }`}
              >
                Limit
              </button>
            </div>
          </div>

          {/* Limit Price Input if LIMIT */}
          {orderType === 'LIMIT' && (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-[#A3A3A3]">Limit Price ($)</label>
              <input
                type="number"
                step="0.1"
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                className="w-full bg-[#000000] border border-[#1A1A1A] rounded-lg px-3 py-2 text-sm text-[#FFFFFF] font-mono focus:outline-none focus:border-[#404040]"
              />
            </div>
          )}

          {/* Quantity Input */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-[#A3A3A3]">Order Quantity</label>
            <input
              type="number"
              step="0.01"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full bg-[#000000] border border-[#1A1A1A] rounded-lg px-3 py-2 text-sm text-[#FFFFFF] font-mono focus:outline-none focus:border-[#404040]"
            />
          </div>

          {/* Notional Readout */}
          <div className="bg-[#121212] p-3 rounded-lg border border-[#1A1A1A] flex items-center justify-between text-xs">
            <span className="text-[#A3A3A3]">Estimated Notional:</span>
            <span className="font-mono font-bold text-[#FFFFFF] text-sm">
              ${totalNotional.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {/* Pre-Trade Guardrail Feedback */}
          {isKillSwitchActive ? (
            <div className="p-2.5 bg-[#141414] border border-rose-900/40 rounded text-xs text-rose-400 flex items-center gap-2 font-mono">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
              <span>Execution Blocked: Kill Switch Active.</span>
            </div>
          ) : isFatFinger ? (
            <div className="p-2.5 bg-[#141414] border border-amber-900/40 rounded text-xs text-amber-400 flex items-center gap-2 font-mono">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>Fat-finger collar breach ($500k max).</span>
            </div>
          ) : (
            <div className="p-2.5 bg-[#141414] border border-[#262626] rounded text-xs text-[#A3A3A3] flex items-center gap-2 font-mono">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span>Pre-trade risk verification passed.</span>
            </div>
          )}

          {feedback && <div className="text-xs text-rose-400 font-semibold">{feedback}</div>}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] rounded-lg text-xs font-medium border border-[#1A1A1A] transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isKillSwitchActive || isFatFinger}
              className={`px-5 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-all shadow-sm ${
                side === 'BUY'
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40'
                  : 'bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-40'
              }`}
            >
              <span>Transmit {side}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
