/**
 * app.json holds the settings. This file only changes what must differ in a store build:
 * push notifications use Apple's production service when EAS builds the "production" profile.
 */
module.exports = ({ config }) => {
  const production = process.env.EAS_BUILD_PROFILE === 'production';
  return {
    ...config,
    plugins: config.plugins.map((p) =>
      Array.isArray(p) && p[0] === 'onesignal-expo-plugin' ? [p[0], { ...p[1], mode: production ? 'production' : 'development' }] : p,
    ),
  };
};
