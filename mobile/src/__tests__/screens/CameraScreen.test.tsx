import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import CameraScreen from '../../screens/CameraScreen';
import { AppProvider } from '../../context/AppContext';
import { NavigationContainer } from '@react-navigation/native';
import { Camera, useCameraDevice, useCameraPermission } from 'react-native-vision-camera';

// Navigation mock
const mockNavigation = {
  navigate: jest.fn(),
  goBack: jest.fn(),
};

const mockRoute = {
  params: {},
};

describe('CameraScreen', () => {
  it('renders correctly when device is found', async () => {
    // mock implementation is already in jest.setup.js, 
    // but we can ensure it's behaving as expected for this test.
    const { getByText } = render(
      <NavigationContainer>
        <AppProvider>
          <CameraScreen navigation={mockNavigation as any} route={mockRoute as any} />
        </AppProvider>
      </NavigationContainer>
    );

    await waitFor(() => {
      expect(getByText('Ready')).toBeTruthy();
    });
  });

  it('shows error when no device is found', async () => {
    (useCameraDevice as jest.Mock).mockReturnValueOnce(null);

    const { getByText } = render(
      <NavigationContainer>
        <AppProvider>
          <CameraScreen navigation={mockNavigation as any} route={mockRoute as any} />
        </AppProvider>
      </NavigationContainer>
    );

    await waitFor(() => {
      expect(getByText('No camera device found')).toBeTruthy();
    });
  });
});
