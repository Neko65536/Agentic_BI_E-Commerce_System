'''
可用于测试的问题列表：

1. 总 GMV 是多少？
2. 每个月 GMV 趋势如何？
3. 哪些品类销售额最高？
4. 评价分数最低的卖家有哪些？
5. 哪些州的订单最多？
6. 平均客单价是多少？
7. 运费最高的品类有哪些？
8. 复购客户占比是多少？
9. 订单取消率是多少？
10. 付款方式分布如何？
'''

from agents.orchestrator_agent import run_orchestrator

result = run_orchestrator("付款方式分布如何？")

print(result["final_answer"])
print()
print("SQL:")
print(result["sql"])
print()
print("前 5 行:")
for row in result["rows"][:5]:
    print(row)

print("\n" + "=" * 80)
result_year = run_orchestrator("2018年付款方式分布如何？")
print(result_year["final_answer"])
print()
print("SQL:")
print(result_year["sql"])
