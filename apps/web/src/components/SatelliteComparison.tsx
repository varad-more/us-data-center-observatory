"use client";

import { useState } from "react";

interface SatelliteComparisonProps {
  projectCode: string;
  className?: string;
}

export function SatelliteComparison({ projectCode, className = "" }: SatelliteComparisonProps) {
  const [position, setPosition] = useState(50);
  
  return (
    <div className={`satellite-comparison ${className}`} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <p className="card-note">
        Simulated Copernicus Sentinel-2 change detection for {projectCode}. Slide to compare "Before" (left) and "After" (right) earth disturbance.
      </p>
      
      <div 
        style={{
          position: "relative",
          width: "100%",
          height: "300px",
          overflow: "hidden",
          borderRadius: "8px",
          border: "1px solid var(--border)",
          cursor: "col-resize",
        }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
          setPosition((x / rect.width) * 100);
        }}
        onTouchMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = Math.max(0, Math.min(e.touches[0].clientX - rect.left, rect.width));
          setPosition((x / rect.width) * 100);
        }}
      >
        {/* After (Bottom Layer - Earth Disturbance) */}
        <div style={{
          position: "absolute",
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: "#8c7355", // Dirt/bare earth color
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "flex-end",
          padding: "1rem",
          color: "rgba(255,255,255,0.7)",
          fontWeight: 600,
          textShadow: "1px 1px 2px rgba(0,0,0,0.8)"
        }}>
          After
        </div>

        {/* Before (Top Layer - Vegetation) */}
        <div style={{
          position: "absolute",
          top: 0, left: 0, bottom: 0,
          width: `${position}%`,
          backgroundColor: "#4a5d23", // Vegetation color
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "flex-start",
          padding: "1rem",
          color: "rgba(255,255,255,0.7)",
          fontWeight: 600,
          overflow: "hidden",
          textShadow: "1px 1px 2px rgba(0,0,0,0.8)"
        }}>
          Before
        </div>

        {/* Slider Handle */}
        <div style={{
          position: "absolute",
          top: 0, bottom: 0,
          left: `${position}%`,
          width: "4px",
          backgroundColor: "#ffffff",
          transform: "translateX(-50%)",
          boxShadow: "0 0 4px rgba(0,0,0,0.5)"
        }}>
          <div style={{
            position: "absolute",
            top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            width: "24px", height: "24px",
            backgroundColor: "#ffffff",
            borderRadius: "50%",
            boxShadow: "0 2px 4px rgba(0,0,0,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
