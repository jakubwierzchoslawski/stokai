/**
 * Manual mock for maplibre-gl.
 *
 * Used by Jest tests that import components depending on maplibre-gl.
 * maplibre-gl is not installed in the Jest environment (it requires a browser/WebGL context);
 * this mock provides the minimal Map constructor stub needed for tests.
 */

const MockMap = jest.fn().mockImplementation(() => ({
  on: jest.fn((event, cb) => {
    if (event === 'load') setTimeout(() => cb(), 0);
  }),
  off: jest.fn(),
  getZoom: jest.fn(() => 2),
  getBounds: jest.fn(() => ({ toArray: () => [[-180, -85], [180, 85]] })),
  flyTo: jest.fn(),
  addLayer: jest.fn(),
  removeLayer: jest.fn(),
  addSource: jest.fn(),
  removeSource: jest.fn(),
  getSource: jest.fn(),
  setPaintProperty: jest.fn(),
  remove: jest.fn(),
}));

module.exports = {
  default: { Map: MockMap },
  Map: MockMap,
};
