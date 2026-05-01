const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

const defaultConfig = getDefaultConfig(__dirname);

const config = {
  resolver: {
    blockList: [
      /.*\/backend\/.*/,
      /.*\/mobile\/venv\/.*/,
      /.*\/android\/app\/build\/.*/,
      /.*\/android\/build\/.*/,
      /.*\/ios\/build\/.*/,
    ],
  },
  maxWorkers: 2,
};

module.exports = mergeConfig(defaultConfig, config);
