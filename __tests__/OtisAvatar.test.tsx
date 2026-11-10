import { render, screen } from '@testing-library/react-native';

import { OtisAvatar } from '@/components/OtisAvatar';

describe('OtisAvatar', () => {
  test('is exposed to screen readers as a single image labelled "OTIS"', async () => {
    await render(<OtisAvatar />);
    const badge = screen.getByLabelText('OTIS');
    expect(badge.props.accessible).toBe(true);
    expect(badge.props.accessibilityRole).toBe('image');
  });

  test('defaults to a 48 pt round badge', async () => {
    await render(<OtisAvatar />);
    expect(screen.getByLabelText('OTIS')).toHaveStyle({ width: 48, height: 48, borderRadius: 24 });
  });

  test.each([24, 36, 96])('renders at the requested size %i with the robot inset to 80%%', async (size) => {
    await render(<OtisAvatar size={size} />);
    expect(screen.getByLabelText('OTIS')).toHaveStyle({ width: size, height: size, borderRadius: size / 2 });

    const imgs = screen.container.queryAll((i) => i.type === 'Image');
    expect(imgs).toHaveLength(1);
    const img = imgs[0];
    expect(img.props.source).toBeTruthy();
    expect(img.props.resizeMode).toBe('contain');
    expect(img.props.style).toMatchObject({ width: size * 0.8, height: size * 0.8 });
  });
});
