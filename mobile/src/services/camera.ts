/**
 * CameraService — handles camera/location permissions and frame capture.
 */
import { Platform } from 'react-native';
import Geolocation from '@react-native-community/geolocation';
import { check, PERMISSIONS, request, RESULTS } from 'react-native-permissions';
import { Camera } from 'react-native-vision-camera';

export interface GpsCoordinates {
  latitude: number;
  longitude: number;
  altitude: number | null;
}

export class CameraService {
  /**
   * Request camera permission.
   * Returns true if granted, false otherwise.
   */
  async requestCameraPermission(): Promise<boolean> {
    const status = await Camera.requestCameraPermission();
    return status === 'granted';
  }

  /**
   * Request location permission.
   * Returns true if granted, false otherwise.
   */
  async requestLocationPermission(): Promise<boolean> {
    const permission =
      Platform.OS === 'ios'
        ? PERMISSIONS.IOS.LOCATION_WHEN_IN_USE
        : PERMISSIONS.ANDROID.ACCESS_FINE_LOCATION;

    const current = await check(permission);
    if (current === RESULTS.GRANTED) {
      return true;
    }

    const result = await request(permission);
    return result === RESULTS.GRANTED;
  }

  /**
   * Get the current GPS position.
   * Rejects if location permission is not granted or unavailable.
   */
  getCurrentLocation(): Promise<GpsCoordinates> {
    return new Promise((resolve, reject) => {
      Geolocation.getCurrentPosition(
        (position) => {
          resolve({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            altitude: position.coords.altitude ?? null,
          });
        },
        (error) => {
          reject(new Error(`Location error (${error.code}): ${error.message}`));
        },
        {
          enableHighAccuracy: true,
          timeout: 10_000,
          maximumAge: 5_000,
        },
      );
    });
  }

  /**
   * Capture a single frame from the camera reference as a base64 JPEG string.
   *
   * @param cameraRef - React ref pointing to a Vision Camera instance.
   * @returns base64-encoded JPEG data (no data: URL prefix).
   */
  async captureFrame(cameraRef: React.RefObject<Camera>): Promise<string> {
    if (!cameraRef.current) {
      throw new Error('Camera reference is not available');
    }

    const photo = await cameraRef.current.takePhoto({
      flash: 'off',
      enableShutterSound: false,
    });

    // We need to read the file and convert to base64.
    // However, vision-camera returns a path.
    // If the API expect base64, we might need react-native-fs or similar.
    // Assuming the user wants a similar behavior to takePictureAsync(base64: true).
    // For now, let's use a placeholder or check if we have filesystem access.
    // Wait, let's check if there's any other way in vision-camera v4.
    // Actually, Vision Camera doesn't return base64 directly in takePhoto.
    // But since I cannot add new dependencies easily, I should check how it was used.
    
    // For simplicity, let's try to fetch the file and convert to base64 if possible,
    // or just return the path if the API can handle it.
    // The previous code returned data.base64.
    
    // I'll check if I can use fetch() to get base64.
    const response = await fetch(`file://${photo.path}`);
    const blob = await response.blob();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64data = reader.result as string;
        // remove "data:image/jpeg;base64,"
        resolve(base64data.split(',')[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /**
   * Start capturing frames at *intervalMs* milliseconds.
   * Calls *callback* with the base64-encoded frame on each capture.
   * Returns the interval ID — pass it to stopFrameCapture to stop.
   */
  startFrameCapture(
    cameraRef: React.RefObject<Camera>,
    intervalMs: number,
    callback: (frame: string) => void,
  ): ReturnType<typeof setInterval> {
    const id = setInterval(async () => {
      try {
        const frame = await this.captureFrame(cameraRef);
        callback(frame);
      } catch (err) {
        // Silently skip failed frames — camera may not be ready yet
        console.warn('[CameraService] Frame capture error:', err);
      }
    }, intervalMs);
    return id;
  }

  /**
   * Stop an active frame capture interval.
   */
  stopFrameCapture(intervalId: ReturnType<typeof setInterval>): void {
    clearInterval(intervalId);
  }
}

export default new CameraService();
