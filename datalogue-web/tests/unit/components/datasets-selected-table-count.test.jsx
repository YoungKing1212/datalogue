// 数据集页面能力卡计数回归测试。
// 关键职责：确保“数据表”能力卡展示当前数据集已选择的数据表数量，而不是数据源 schema 全量表数量。
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { DatasetsScreen } from '../../../src/components/datasets';

vi.mock('../../../src/components/analysis-blueprints', () => ({
  AnalysisBlueprintsPanel: () => <div data-testid="analysis-blueprints-panel" />,
}));

const api = vi.hoisted(() => ({
  listDatasets: vi.fn(),
  createDataset: vi.fn(),
  updateDataset: vi.fn(),
  renameDataset: vi.fn(),
  deleteDataset: vi.fn(),
  listDatasetMetrics: vi.fn(),
  createMetric: vi.fn(),
  deleteMetric: vi.fn(),
  updateMetric: vi.fn(),
  listDatasetDimensions: vi.fn(),
  createDimension: vi.fn(),
  deleteDimension: vi.fn(),
  updateDimension: vi.fn(),
  listDatasources: vi.fn(),
  syncDatasourceTables: vi.fn(),
  listSourceTables: vi.fn(),
  getSourceTableColumns: vi.fn(),
  annotateDatasetColumns: vi.fn(),
  importDatasetYaml: vi.fn(),
  exportDatasetYaml: vi.fn(),
  previewTable: vi.fn(),
  streamChat: vi.fn(),
  selectTablesForDataset: vi.fn(),
  deselectTableFromDataset: vi.fn(),
  listSelectedTables: vi.fn(),
  listSelectedColumns: vi.fn(),
  updateSourceColumn: vi.fn(),
  convertColumnToMetric: vi.fn(),
  convertColumnToDimension: vi.fn(),
  updateColumnReviewStatus: vi.fn(),
  listBusinessTerms: vi.fn(),
  createBusinessTerm: vi.fn(),
  updateBusinessTerm: vi.fn(),
  deleteBusinessTerm: vi.fn(),
  linkBusinessTermAssets: vi.fn(),
  discoverBusinessTerms: vi.fn(),
  checkBusinessTermConflicts: vi.fn(),
  listSemanticValidationCases: vi.fn(),
  createSemanticValidationCase: vi.fn(),
  getDatasetSubAgentManifest: vi.fn(),
  saveDatasetSubAgentManifest: vi.fn(),
  publishDatasetSubAgentManifest: vi.fn(),
  rollbackDatasetSubAgentManifest: vi.fn(),
  routeCheckDatasetSubAgentManifest: vi.fn(),
}));

vi.mock('../../../src/api/client', () => api);

describe('DatasetsScreen selected table count', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    api.listDatasets.mockResolvedValue([
      { id: 7, name: '零售数据集', datasource_id: 11 },
    ]);
    api.listDatasources.mockResolvedValue([
      { id: 11, name: '零售库' },
    ]);
    api.listDatasetMetrics.mockResolvedValue([]);
    api.listDatasetDimensions.mockResolvedValue([]);
    api.listBusinessTerms.mockResolvedValue([]);
    api.listSemanticValidationCases.mockResolvedValue([]);
    api.getDatasetSubAgentManifest.mockResolvedValue({});
    api.listSourceTables.mockResolvedValue([
      { id: 101, datasource_id: 11, schema_name: 'public', table_name: 'orders', column_count: 4, status: 'synced' },
      { id: 102, datasource_id: 11, schema_name: 'public', table_name: 'customers', column_count: 5, status: 'synced' },
      { id: 103, datasource_id: 11, schema_name: 'public', table_name: 'stores', column_count: 6, status: 'synced' },
    ]);
    api.listSelectedTables.mockResolvedValue([
      { id: 101, datasource_id: 11, schema_name: 'public', table_name: 'orders', column_count: 4, status: 'synced' },
    ]);
    api.listSelectedColumns.mockResolvedValue([]);
    api.previewTable.mockResolvedValue({ columns: [], rows: [] });
  });

  it('数据表能力卡只显示已选择表数量', async () => {
    render(<DatasetsScreen />);

    const dataTableTab = await screen.findByRole('button', { name: /数据表/ });

    await waitFor(() => {
      expect(within(dataTableTab).getByText('1')).toBeInTheDocument();
    });
    expect(within(dataTableTab).queryByText('3')).not.toBeInTheDocument();
  });
});
