## Acknowledgments

No external funding was received for this research. The qengine execution engine used for all reported backtests builds on the open-source Jesse trading framework; the author thanks the Jesse maintainers for the upstream foundation on which the CFD/forex extensions reported here were developed.

## Declaration of Interest

The author declares that there are no competing interests associated with this manuscript.

## Data Availability Statement

The data used in this study consist of EUR-USD foreign exchange price data at 1-minute resolution, sourced from OANDA Corporation. It covers the period from January 1, 2020, to April 20, 2026, and can be accessed by anyone who creates a demo account and easily extracted via OANDA API. The author has complied with all relevant data usage agreements and ethical guidelines in the acquisition and use of this data for research purposes.
The processed feature matrices, the trained regime tree, the evolved island populations, the IslandPilot pipeline source, and the qengine execution engine used for all backtests are publicly available at **https://github.com/hi-naresh/qengine/tree/dev**. The repository documents the steps required to reproduce the Section 6 results from raw OANDA candles through trained model to out-of-sample evaluation, so reviewers and independent researchers can re-run every reported experiment under identical engine, cost-model, and data conditions.

## Disclaimer

The views and conclusions contained in this document are those of the author and should not be interpreted as representing the official policies, either expressed or implied, of any organization or entity. The author assumes no responsibility for any errors or omissions in the content of this manuscript, nor for any actions taken based on the information provided herein. The use of any trade names, commercial products, or organizations does not imply endorsement by the author. The use of pipelines, algorithms, and models described in this manuscript is at the reader's own risk, and the author disclaims any liability for any outcomes resulting from their application.

## Use of Generative AI

Generative AI tools were used in the preparation of this manuscript exclusively for English language refinement and clarity of expression. No AI tool was used to interpret, or validate any quantitative results, code, or analytical conclusions. All data analysis, model design, evolutionary algorithm implementation, regime tree construction, fitness function design, hyperparameter selection, statistical interpretation, and critical reading of empirical findings are solely the work of the author. AI-assisted edits were limited to wording and did not affect the substance; in every instance, the author retained final editorial control and verified that the edited prose accurately conveyed the intended technical claims.