// Configuración del motor Remotion. Codec, CRF y preset NO van aquí: los pasa scripts/remotion.py
// desde config.json > remotion (una sola fuente de verdad), igual que el motor promo.
import { Config } from '@remotion/cli/config';

Config.setEntryPoint('./src/index.ts');
Config.setOverwriteOutput(true);
Config.setVideoImageFormat('jpeg');
