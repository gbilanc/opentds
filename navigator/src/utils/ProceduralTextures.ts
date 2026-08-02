import * as THREE from 'three';

/**
 * Generates procedural textures using Canvas API.
 * No external image files needed — everything is drawn at runtime.
 */
export class ProceduralTextures {

  /** Grass texture: green base with subtle noise */
  static grass(width = 256, height = 256): THREE.CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    // Base green
    ctx.fillStyle = '#4a7c3f';
    ctx.fillRect(0, 0, width, height);

    // Noise grain
    const imageData = ctx.getImageData(0, 0, width, height);
    for (let i = 0; i < imageData.data.length; i += 4) {
      const noise = (Math.random() - 0.5) * 30;
      imageData.data[i] = Math.min(255, Math.max(0, imageData.data[i] + noise));
      imageData.data[i + 1] = Math.min(255, Math.max(0, imageData.data[i + 1] + noise));
      imageData.data[i + 2] = Math.min(255, Math.max(0, imageData.data[i + 2] + noise - 10));
    }
    ctx.putImageData(imageData, 0, 0);

    // Subtle horizontal streaks
    ctx.strokeStyle = 'rgba(0,0,0,0.05)';
    ctx.lineWidth = 1;
    for (let y = 0; y < height; y += 8) {
      ctx.beginPath();
      ctx.moveTo(0, y + Math.random() * 4);
      ctx.lineTo(width, y + Math.random() * 4);
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(4, 4);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  /** Wood plank texture */
  static wood(width = 256, height = 256): THREE.CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    // Base
    ctx.fillStyle = '#8B6914';
    ctx.fillRect(0, 0, width, height);

    // Wood grain lines
    for (let y = 0; y < height; y += 3 + Math.random() * 5) {
      const alpha = 0.05 + Math.random() * 0.15;
      ctx.strokeStyle = `rgba(0,0,0,${alpha})`;
      ctx.lineWidth = 1 + Math.random() * 2;
      ctx.beginPath();
      ctx.moveTo(0, y);
      for (let x = 0; x < width; x += 20) {
        ctx.lineTo(x, y + (Math.random() - 0.5) * 3);
      }
      ctx.stroke();
    }

    // Plank separators
    ctx.strokeStyle = 'rgba(0,0,0,0.3)';
    ctx.lineWidth = 2;
    const plankHeight = height / 3;
    for (let i = 0; i < 3; i++) {
      const y = i * plankHeight + Math.random() * 4;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  /** Stone / gravel texture */
  static stone(width = 256, height = 256): THREE.CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    // Base grey
    ctx.fillStyle = '#808080';
    ctx.fillRect(0, 0, width, height);

    // Stone blocks
    const blockSize = 40;
    for (let x = 0; x < width; x += blockSize) {
      for (let y = 0; y < height; y += blockSize) {
        const shade = 100 + Math.random() * 100;
        ctx.fillStyle = `rgb(${shade},${shade},${shade})`;
        const bx = x + (Math.random() - 0.5) * 6;
        const by = y + (Math.random() - 0.5) * 6;
        const bw = blockSize - 2 + (Math.random() - 0.5) * 4;
        const bh = blockSize - 2 + (Math.random() - 0.5) * 4;
        ctx.fillRect(bx, by, bw, bh);

        // Mortar gaps
        ctx.strokeStyle = 'rgba(0,0,0,0.3)';
        ctx.lineWidth = 1;
        ctx.strokeRect(bx, by, bw, bh);
      }
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(2, 2);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  /** Gravel / ghiaia texture: multicolored pebbles on grey ground */
  static gravel(width = 512, height = 512): THREE.CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    // Base grey-brown
    ctx.fillStyle = '#8a8a7c';
    ctx.fillRect(0, 0, width, height);

    // Noise grain for fine texture
    const imageData = ctx.getImageData(0, 0, width, height);
    for (let i = 0; i < imageData.data.length; i += 4) {
      const noise = (Math.random() - 0.5) * 35;
      imageData.data[i] = Math.min(255, Math.max(0, imageData.data[i] + noise));
      imageData.data[i + 1] = Math.min(255, Math.max(0, imageData.data[i + 1] + noise));
      imageData.data[i + 2] = Math.min(255, Math.max(0, imageData.data[i + 2] + noise));
    }
    ctx.putImageData(imageData, 0, 0);

    // Draw random pebbles/stones of varying sizes and colors
    const pebbleColors = [
      '#9e9e8e', '#b0a89a', '#8e8a7a', '#a09888', '#7a7a6e',
      '#c4b8a8', '#968e80', '#aaa290', '#828272', '#b8b0a0',
      '#6e6e60', '#9a9282', '#aea698', '#868478', '#a4a090',
    ];

    for (let i = 0; i < 400; i++) {
      const px = Math.random() * width;
      const py = Math.random() * height;
      const r = 3 + Math.random() * 8; // radius 3-11px

      // Pebble shadow
      ctx.fillStyle = 'rgba(0,0,0,0.15)';
      ctx.beginPath();
      ctx.ellipse(px + 1, py + 1, r, r * 0.7, Math.random() * Math.PI, 0, Math.PI * 2);
      ctx.fill();

      // Pebble body
      ctx.fillStyle = pebbleColors[Math.floor(Math.random() * pebbleColors.length)];
      ctx.beginPath();
      ctx.ellipse(px, py, r, r * 0.7, Math.random() * Math.PI, 0, Math.PI * 2);
      ctx.fill();

      // Subtle highlight
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.beginPath();
      ctx.ellipse(px - r * 0.2, py - r * 0.2, r * 0.4, r * 0.25, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // Fine mortar/dirt between pebbles
    ctx.fillStyle = 'rgba(100,95,85,0.10)';
    for (let i = 0; i < 150; i++) {
      const px = Math.random() * width;
      const py = Math.random() * height;
      ctx.beginPath();
      ctx.arc(px, py, 1.5 + Math.random() * 3, 0, Math.PI * 2);
      ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(3, 3);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  /** Dirt path texture */
  static dirt(width = 256, height = 256): THREE.CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    // Base brown
    ctx.fillStyle = '#8B7355';
    ctx.fillRect(0, 0, width, height);

    // Noise
    const imageData = ctx.getImageData(0, 0, width, height);
    for (let i = 0; i < imageData.data.length; i += 4) {
      const noise = (Math.random() - 0.5) * 40;
      imageData.data[i] = Math.min(255, Math.max(0, imageData.data[i] + noise));
      imageData.data[i + 1] = Math.min(255, Math.max(0, imageData.data[i + 1] + noise - 10));
      imageData.data[i + 2] = Math.min(255, Math.max(0, imageData.data[i + 2] + noise - 20));
    }
    ctx.putImageData(imageData, 0, 0);

    // Pebbles
    for (let i = 0; i < 50; i++) {
      const px = Math.random() * width;
      const py = Math.random() * height;
      const r = 2 + Math.random() * 4;
      ctx.fillStyle = `rgba(0,0,0,${0.1 + Math.random() * 0.2})`;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(3, 3);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  /** Roof tile texture */
  static roof(width = 256, height = 256): THREE.CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    ctx.fillStyle = '#6B3A2E';
    ctx.fillRect(0, 0, width, height);

    // Tile rows
    const rowH = 20;
    for (let y = 0; y < height; y += rowH) {
      const offset = (Math.floor(y / rowH) % 2) * 20;
      for (let x = -20 + offset; x < width; x += 40) {
        const shade = 60 + Math.random() * 50;
        ctx.fillStyle = `rgb(${shade + 40},${shade * 0.5},${shade * 0.35})`;
        ctx.fillRect(x + 1, y + 1, 38, 18);
        ctx.strokeStyle = 'rgba(0,0,0,0.2)';
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 1, y + 1, 38, 18);
      }
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }
}
