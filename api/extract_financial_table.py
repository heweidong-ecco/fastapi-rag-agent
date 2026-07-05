"""
财报表格提取与验证脚本
使用 pdfplumber 提取阿里巴巴2023财年报告中的财务数据表格。
"""
import pdfplumber
import sys
import os

# 请替换为你实际的财报 PDF 路径
PDF_PATH = "../阿里巴巴集團-2023財務年度報告.pdf"

def extract_tables_from_pdf(pdf_path: str, target_pages: list = None):
    """提取 PDF 中指定页面的所有表格"""
    tables_data = []
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"PDF 总页数: {total_pages}")
        
        # 如果未指定页面，则扫描所有页
        pages_to_scan = target_pages if target_pages else range(total_pages)
        
        for page_num in pages_to_scan:
            # pdfplumber 页面从 0 开始，报告页码从 1 开始
            page = pdf.pages[page_num]
            tables = page.extract_tables()
            
            if tables:
                print(f"\n第 {page_num+1} 页：发现 {len(tables)} 个表格")
                for table_idx, table in enumerate(tables):
                    print(f"\n--- 表格 {table_idx+1} ---")
                    # 清理表格数据（去除 None，替换换行符）
                    cleaned_table = []
                    for row in table:
                        cleaned_row = [
                            str(cell).replace('\n', ' ').strip() if cell else ''
                            for cell in row
                        ]
                        cleaned_table.append(cleaned_row)
                    
                    tables_data.append({
                        "page": page_num + 1,
                        "table_index": table_idx + 1,
                        "data": cleaned_table
                    })
                    
                    # 打印表格前5行作为预览
                    print(f"（共 {len(cleaned_table)} 行，以下为前5行预览）")
                    for row in cleaned_table[:5]:
                        print(" | ".join(row))
                    
                    if len(cleaned_table) > 5:
                        print(f"... 剩余 {len(cleaned_table)-5} 行")
            else:
                # 只对用户指定的页面打印无表格提示
                if target_pages:
                    print(f"第 {page_num+1} 页：无表格")
    
    return tables_data


def verify_table_cell(tables_data: list, page: int, table_idx: int, row: int, col: int, expected_value: str):
    """
    验证某个单元格的值是否与预期一致。
    page: PDF 页码（从 1 开始）
    table_idx: 该页中表格的索引（从 1 开始）
    row: 行号（从 0 开始，表头行算第0行）
    col: 列号（从 0 开始）
    expected_value: 你在 PDF 中看到的原始数字（字符串形式）
    """
    for t in tables_data:
        if t["page"] == page and t["table_index"] == table_idx:
            data = t["data"]
            if row < len(data) and col < len(data[row]):
                actual = data[row][col]
                if actual.replace(',', '') == expected_value.replace(',', ''):
                    print(f"✅ 验证通过：第{page}页 表格{table_idx} 行{row}列{col} = {actual}")
                else:
                    print(f"❌ 验证失败：预期 {expected_value}，实际 {actual}")
                return
    print(f"❌ 未找到目标单元格：第{page}页 表格{table_idx} 行{row}列{col}")


if __name__ == "__main__":
    if not os.path.exists(PDF_PATH):
        print(f"找不到文件：{PDF_PATH}，请修改脚本中的 PDF_PATH 变量。")
        sys.exit(1)
    
    # 提取财报中常见的财务数据页面
    # 阿里巴巴2023财年报告中，合并利润表在第 200 页左右（具体页码需根据你的PDF调整）
    # 建议先用少量页面测试，确认页码后再扩大范围
    target_pages = [199, 200, 201]  # 示例：利润表附近的几页，请根据实际PDF页码调整
    
    print(f"正在从 {PDF_PATH} 提取表格...")
    tables = extract_tables_from_pdf(PDF_PATH, target_pages)
    
    if not tables:
        print("未在指定页面发现表格。建议用以下命令预览PDF前几页，确认表格所在页码：")
        print(f"   python -c \"import pdfplumber; pdf=pdfplumber.open('{PDF_PATH}'); page=pdf.pages[0]; print(page.extract_text()[:500])\"")
        sys.exit(0)
    
    print(f"\n===== 提取完成，共发现 {len(tables)} 个表格 =====")
    
    # 示例：验证某个已知单元格（需要打开PDF手动确认后填写预期值）
    print("\n===== 开始验证（示例）=====")
    # 下面这行是示例，你需要打开PDF找到确切的数字后替换
    verify_table_cell(tables, page=200, table_idx=1, row=2, col=1, expected_value="717,200")
    
    print("\n请对照原始 PDF 逐项检查数字是否准确。")


    