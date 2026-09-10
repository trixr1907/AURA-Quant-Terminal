'use strict';

/**
 * Return the pre-registered EXP-025 anchored, t1-safe fold geometry.
 * Indicator warmup and test-boundary semantics match the engine.
 */
function fairFoldBoundaries(n, tfMinutes, K = 4, warmup = 235) {
  const effWarmup = Math.min(warmup, Math.max(14, n - 60));
  const minTrainBars = tfMinutes >= 240 ? 500 : 2000;
  const firstTestStart = effWarmup + minTrainBars + 1;
  const lastSignalIdx = n - 2;
  const testableBars = Math.max(0, lastSignalIdx - firstTestStart + 1);
  const testFoldSize = Math.floor(testableBars / K);
  const trainStart = effWarmup;
  const folds = [];

  for (let k = 0; k < K; k++) {
    const testStart = firstTestStart + k * testFoldSize;
    const testEnd = k === K - 1 ? n - 2 : testStart + testFoldSize - 1;
    const trainEnd = testStart - 2;
    const trainBars = trainEnd - trainStart + 1;
    const testBars = testEnd - testStart + 1;
    folds.push({
      fold: k + 1,
      trainRange: [trainStart, trainEnd],
      testRange: [testStart, testEnd],
      trainBars,
      trainHours: trainBars * tfMinutes / 60,
      testBars,
      testHours: testBars * tfMinutes / 60
    });
  }

  return { effWarmup, minTrainBars, folds };
}

module.exports = { fairFoldBoundaries };
