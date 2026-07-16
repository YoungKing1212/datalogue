// 数据集页面能力卡计数回归测试。
// 关键职责：确保“数据表”能力卡展示当前数据集已选择的数据表数量，而不是数据源 schema 全量表数量。
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  getDatasourceSchemas: vi.fn(),
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
      { id: 7, name: '零售数据集', datasource_id: 11, schema_name: 'public' },
    ]);
    api.listDatasources.mockResolvedValue([
      { id: 11, name: '零售库', default_schema: 'public', database_name: 'retail' },
    ]);
    api.getDatasourceSchemas.mockResolvedValue({ schemas: ['public', 'archive'] });
    api.createDataset.mockResolvedValue({ id: 8 });
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
    expect(api.listSourceTables).toHaveBeenCalledWith(11, 'public');
  }, 10000);

  it('新建数据集时加载并提交所选 Schema', async () => {
    api.listDatasets
      .mockResolvedValueOnce([
        { id: 7, name: '零售数据集', datasource_id: 11, schema_name: 'public' },
      ])
      .mockResolvedValue([
        { id: 8, name: '归档数据集', datasource_id: 11, schema_name: 'archive' },
        { id: 7, name: '零售数据集', datasource_id: 11, schema_name: 'public' },
      ]);
    api.listSourceTables.mockImplementation((_datasourceId, schema) => Promise.resolve(
      schema === 'archive' ? [] : [
        { id: 101, datasource_id: 11, schema_name: 'public', table_name: 'orders' },
      ],
    ));
    api.syncDatasourceTables.mockResolvedValue({ ok: true, total_tables: 1 });
    render(<DatasetsScreen />);

    fireEvent.click(screen.getByRole('button', { name: /新建数据集/ }));
    fireEvent.change(screen.getByPlaceholderText('如: 零售业务数据集'), {
      target: { value: '归档数据集' },
    });
    fireEvent.click(screen.getByRole('button', { name: '请选择数据源' }));
    fireEvent.click(await screen.findByText('零售库'));

    await waitFor(() => expect(api.getDatasourceSchemas).toHaveBeenCalledWith(11));
    expect(screen.getByRole('button', { name: 'public' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'public' }));
    fireEvent.click(screen.getByText('archive'));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    await waitFor(() => {
      expect(api.syncDatasourceTables).toHaveBeenCalledWith(11, 'archive');
      expect(api.createDataset).toHaveBeenCalledWith(expect.objectContaining({
        name: '归档数据集',
        datasource_id: 11,
        schema_name: 'archive',
      }));
    });
  }, 10000);
});
